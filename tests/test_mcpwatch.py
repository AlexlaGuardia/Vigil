"""Tests for vigil.mcpwatch — MCP production observability."""

import asyncio
import time
import tempfile
import os
import pytest

from vigil.db import VigilDB
from vigil.mcpwatch import MCPWatch, ToolEvent, ToolStats, instrument


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    """Create a temporary Vigil database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = VigilDB(db_path)
    yield db
    os.unlink(db_path)


@pytest.fixture
def watch(tmp_db):
    """Create an MCPWatch instance with local DB."""
    return MCPWatch(server_name="test-server", db=tmp_db)


@pytest.fixture
def watch_no_db():
    """Create an MCPWatch instance without DB (memory only)."""
    return MCPWatch(server_name="test-server")


# ── ToolEvent tests ──────────────────────────────────────────────

class TestToolEvent:
    def test_to_dict(self):
        e = ToolEvent(
            server_name="srv",
            tool_name="search",
            duration_ms=42.5,
            status="success",
        )
        d = e.to_dict()
        assert d["server_name"] == "srv"
        assert d["tool_name"] == "search"
        assert d["duration_ms"] == 42.5
        assert d["status"] == "success"
        assert d["error"] is None
        assert "created_at" in d

    def test_error_event(self):
        e = ToolEvent(
            server_name="srv",
            tool_name="failing_tool",
            duration_ms=10.0,
            status="error",
            error="ValueError: bad input",
        )
        d = e.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "ValueError: bad input"


# ── ToolStats tests ──────────────────────────────────────────────

class TestToolStats:
    def test_empty_stats(self):
        s = ToolStats(name="test")
        assert s.call_count == 0
        assert s.avg_ms == 0.0
        assert s.p95_ms == 0.0
        assert s.error_rate == 0.0

    def test_record_calls(self):
        s = ToolStats(name="test")
        s.record(100.0)
        s.record(200.0)
        s.record(300.0)
        assert s.call_count == 3
        assert s.avg_ms == 200.0
        assert s.min_ms == 100.0
        assert s.max_ms == 300.0
        assert s.error_count == 0

    def test_record_errors(self):
        s = ToolStats(name="test")
        s.record(100.0)
        s.record(200.0, is_error=True)
        assert s.error_count == 1
        assert s.error_rate == 0.5

    def test_percentiles(self):
        s = ToolStats(name="test")
        for i in range(100):
            s.record(float(i))
        assert s.p95_ms == 95.0
        assert s.p99_ms == 99.0

    def test_to_dict(self):
        s = ToolStats(name="test")
        s.record(50.0)
        s.record(100.0, is_error=True)
        d = s.to_dict()
        assert d["name"] == "test"
        assert d["call_count"] == 2
        assert d["error_count"] == 1
        assert d["error_rate"] == 0.5
        assert d["avg_ms"] == 75.0

    def test_duration_buffer_capped(self):
        s = ToolStats(name="test")
        for i in range(1200):
            s.record(float(i))
        assert len(s.durations) == 1000
        assert s.call_count == 1200


# ── MCPWatch core tests ─────────────────────────────────────────

class TestMCPWatch:
    def test_health_initial(self, watch):
        h = watch.health()
        assert h["server"] == "test-server"
        assert h["status"] == "healthy"
        assert h["total_calls"] == 0
        assert h["tools_monitored"] == 0

    def test_record_updates_stats(self, watch):
        watch._record("search", 42.0, "success", None)
        watch._record("search", 58.0, "success", None)
        assert watch._total_calls == 2
        assert watch._total_errors == 0
        assert "search" in watch._stats
        assert watch._stats["search"].call_count == 2

    def test_record_error(self, watch):
        watch._record("bad_tool", 10.0, "error", "RuntimeError: boom")
        assert watch._total_errors == 1
        assert len(watch._recent_errors) == 1
        assert watch._recent_errors[0].error == "RuntimeError: boom"

    def test_health_status_degraded(self, watch):
        for i in range(10):
            watch._record("tool", 10.0, "success", None)
        for i in range(3):
            watch._record("tool", 10.0, "error", "fail")
        h = watch.health()
        assert h["status"] == "degraded"  # 3/13 > 0.1

    def test_health_status_unhealthy(self, watch):
        for i in range(5):
            watch._record("tool", 10.0, "error", "fail")
        h = watch.health()
        assert h["status"] == "unhealthy"  # 5/5 = 1.0 > 0.5

    def test_tool_stats(self, watch):
        watch._record("search", 42.0, "success", None)
        stats = watch.tool_stats("search")
        assert stats["name"] == "search"
        assert stats["call_count"] == 1
        assert stats["avg_ms"] == 42.0

    def test_tool_stats_not_found(self, watch):
        assert watch.tool_stats("nonexistent") is None

    def test_recent_errors(self, watch):
        watch._record("tool", 10.0, "error", "err1")
        watch._record("tool", 10.0, "error", "err2")
        errors = watch.recent_errors()
        assert len(errors) == 2
        assert errors[0]["error"] == "err1"

    def test_reset(self, watch):
        watch._record("tool", 10.0, "success", None)
        assert watch._total_calls == 1
        watch.reset()
        assert watch._total_calls == 0
        assert len(watch._stats) == 0

    def test_is_silent_false_initially(self, watch):
        assert not watch.is_silent()

    def test_db_persistence(self, watch, tmp_db):
        watch._record("search", 42.0, "success", None)
        watch._record("search", 99.0, "error", "boom")
        # Verify in DB
        rows = tmp_db.query_all("SELECT * FROM mcp_events WHERE server_name = 'test-server'")
        assert len(rows) == 2
        assert rows[0]["tool_name"] == "search"

    def test_db_tool_stats(self, watch):
        watch._record("search", 42.0, "success", None)
        watch._record("search", 99.0, "error", "boom")
        watch._record("fetch", 10.0, "success", None)
        stats = watch.db_tool_stats(hours=1)
        assert len(stats) == 2

    def test_db_recent_errors(self, watch):
        watch._record("search", 99.0, "error", "boom")
        errors = watch.db_recent_errors()
        assert len(errors) == 1
        assert errors[0]["error"] == "boom"

    def test_db_latency_percentiles(self, watch):
        for i in range(100):
            watch._record("tool", float(i), "success", None)
        p = watch.db_latency_percentiles(hours=1)
        assert p["count"] == 100
        assert p["p50"] > 0
        assert p["p95"] > p["p50"]

    def test_no_db_mode(self, watch_no_db):
        watch_no_db._record("tool", 42.0, "success", None)
        assert watch_no_db._total_calls == 1
        # DB queries return empty
        assert watch_no_db.db_tool_stats() == []
        assert watch_no_db.db_recent_errors() == []


# ── Wrapper tests ────────────────────────────────────────────────

class TestWrapper:
    def test_wrap_sync_function(self, watch):
        def my_tool(x):
            return x * 2

        wrapped = watch._wrap("my_tool", my_tool)
        result = wrapped(5)
        assert result == 10
        assert watch._total_calls == 1
        assert watch._stats["my_tool"].call_count == 1

    def test_wrap_sync_error(self, watch):
        def failing_tool():
            raise ValueError("bad")

        wrapped = watch._wrap("failing", failing_tool)
        with pytest.raises(ValueError):
            wrapped()
        assert watch._total_errors == 1
        assert watch._stats["failing"].error_count == 1

    def test_wrap_async_function(self, watch):
        async def my_async_tool(x):
            return x * 3

        wrapped = watch._wrap("async_tool", my_async_tool)
        result = asyncio.run(wrapped(5))
        assert result == 15
        assert watch._total_calls == 1

    def test_wrap_async_error(self, watch):
        async def failing_async():
            raise RuntimeError("async boom")

        wrapped = watch._wrap("async_fail", failing_async)
        with pytest.raises(RuntimeError):
            asyncio.run(wrapped())
        assert watch._total_errors == 1

    def test_wrap_measures_duration(self, watch):
        def slow_tool():
            time.sleep(0.05)
            return "done"

        wrapped = watch._wrap("slow", slow_tool)
        wrapped()
        stats = watch._stats["slow"]
        assert stats.avg_ms >= 40  # at least 40ms (sleep 50ms with margin)


# ── Instrument function tests ────────────────────────────────────

class TestInstrument:
    def test_instrument_with_db_path(self, tmp_db):
        """Test instrument() with db_path parameter creates MCPWatch."""

        class FakeToolManager:
            def __init__(self):
                self.tools = {}

        class FakeServer:
            name = "fake-server"
            _tool_manager = FakeToolManager()

        server = FakeServer()
        watch = instrument(server, db_path=tmp_db.path)
        assert watch.server_name == "fake-server"
        assert watch.db is not None

    def test_instrument_wraps_tools(self, tmp_db):
        """Test instrument() wraps registered tools."""

        call_log = []

        async def original_fn(x: str) -> str:
            call_log.append(x)
            return f"result: {x}"

        class FakeTool:
            def __init__(self, fn):
                self.fn = fn

        class FakeToolManager:
            def __init__(self):
                self.tools = {"test_tool": FakeTool(original_fn)}

        class FakeServer:
            name = "test-srv"
            _tool_manager = FakeToolManager()

        server = FakeServer()
        watch = instrument(server, db_path=tmp_db.path)

        # The tool's fn should now be wrapped
        wrapped_fn = server._tool_manager.tools["test_tool"].fn
        assert wrapped_fn is not original_fn  # It was wrapped

        # Call it and verify monitoring
        result = asyncio.run(wrapped_fn("hello"))
        assert result == "result: hello"
        assert call_log == ["hello"]
        assert watch._total_calls == 1
        assert "test_tool" in watch._stats

    def test_instrument_no_tool_manager(self):
        """Test instrument() handles servers without _tool_manager gracefully."""

        class BareServer:
            name = "bare"

        server = BareServer()
        watch = instrument(server)
        assert watch.server_name == "bare"
        assert watch._total_calls == 0


# ── Low-level Server instrumentation tests ──────────────────────

class TestLowLevelServer:
    """Verify instrument() wraps the low-level mcp.server.lowlevel.Server."""

    def _build_server(self, handler_fn=None):
        """Build a low-level Server with a registered call_tool handler."""
        from mcp.server.lowlevel import Server

        server = Server("low-level-test")

        async def default_handler(name, arguments):
            return [{"type": "text", "text": f"got {name}"}]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict):
            if handler_fn:
                return await handler_fn(name, arguments)
            return await default_handler(name, arguments)

        return server

    def _make_request(self, tool_name, arguments=None):
        from mcp.types import CallToolRequest, CallToolRequestParams
        return CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=tool_name, arguments=arguments or {}),
        )

    def test_instrument_wraps_call_tool_dispatcher(self, tmp_db):
        from mcp.types import CallToolRequest

        server = self._build_server()
        original_handler = server.request_handlers[CallToolRequest]

        watch = instrument(server, db_path=tmp_db.path)
        wrapped_handler = server.request_handlers[CallToolRequest]

        assert wrapped_handler is not original_handler
        assert watch.server_name == "low-level-test"

    def test_low_level_records_call(self, tmp_db):
        from mcp.types import CallToolRequest

        server = self._build_server()
        watch = instrument(server, db_path=tmp_db.path)

        handler = server.request_handlers[CallToolRequest]
        asyncio.run(handler(self._make_request("echo", {"x": 1})))

        assert watch._total_calls == 1
        assert "echo" in watch._stats
        assert watch._stats["echo"].call_count == 1

    def test_low_level_per_tool_attribution(self, tmp_db):
        from mcp.types import CallToolRequest

        server = self._build_server()
        watch = instrument(server, db_path=tmp_db.path)
        handler = server.request_handlers[CallToolRequest]

        asyncio.run(handler(self._make_request("alpha")))
        asyncio.run(handler(self._make_request("beta")))
        asyncio.run(handler(self._make_request("alpha")))

        assert watch._stats["alpha"].call_count == 2
        assert watch._stats["beta"].call_count == 1
        assert watch._total_calls == 3

    def test_low_level_records_errors(self, tmp_db):
        """Low-level Server wraps user exceptions as CallToolResult(isError=True)
        rather than propagating. MCPWatch must detect this from the result."""
        from mcp.types import CallToolRequest

        async def boom(name, arguments):
            raise RuntimeError("low-level boom")

        server = self._build_server(handler_fn=boom)
        watch = instrument(server, db_path=tmp_db.path)
        handler = server.request_handlers[CallToolRequest]

        # Server catches the error — handler returns normally with isError=True
        result = asyncio.run(handler(self._make_request("crashy")))
        assert getattr(result.root, "isError", False) is True

        assert watch._total_errors == 1
        assert watch._stats["crashy"].error_count == 1
        assert "low-level boom" in watch._recent_errors[0].error

    def test_low_level_measures_latency(self, tmp_db):
        from mcp.types import CallToolRequest

        async def slow(name, arguments):
            await asyncio.sleep(0.05)
            return [{"type": "text", "text": "ok"}]

        server = self._build_server(handler_fn=slow)
        watch = instrument(server, db_path=tmp_db.path)
        handler = server.request_handlers[CallToolRequest]

        asyncio.run(handler(self._make_request("slow_tool")))
        assert watch._stats["slow_tool"].avg_ms >= 40

    def test_low_level_handler_unchanged_when_call_tool_missing(self, tmp_db):
        """Server with no @call_tool registered should not crash instrument()."""
        from mcp.server.lowlevel import Server

        server = Server("no-tools")
        watch = instrument(server, db_path=tmp_db.path)
        assert watch.server_name == "no-tools"


# ── Silent-failure detection tests ───────────────────────────────

class _FakeResult:
    """Stand-in for a content-bearing result object (CallToolResult-like)."""
    def __init__(self, content, is_error=False):
        self.content = content
        self.isError = is_error


class TestSilentClassifier:
    """Unit tests for the _is_silent_result / _content_is_empty heuristics."""

    @pytest.mark.parametrize("value", [
        None,
        "",
        "   ",
        "\n\t ",
        b"",
        [],
        (),
        {"content": []},
        {"content": [{"type": "text", "text": ""}]},
        {"content": [{"type": "text", "text": "  "}]},
        [{"type": "text", "text": ""}],
        _FakeResult(content=[]),
        _FakeResult(content=[{"type": "text", "text": "   "}]),
    ])
    def test_silent_values(self, watch_no_db, value):
        assert watch_no_db._is_silent_result(value) is True

    @pytest.mark.parametrize("value", [
        "result",
        "0",
        0,            # legit falsy — NOT silent
        False,        # legit falsy — NOT silent
        {"a": 1},     # populated dict — NOT silent
        {},           # empty dict is ambiguous; treated as NOT silent (conservative)
        [{"type": "text", "text": "hello"}],
        {"content": [{"type": "text", "text": "hi"}]},
        {"content": [{"type": "image", "data": "..."}]},   # non-text payload = real
        _FakeResult(content=[{"type": "text", "text": "ok"}]),
        _FakeResult(content=[], is_error=True),            # explicit error, not silent
    ])
    def test_non_silent_values(self, watch_no_db, value):
        assert watch_no_db._is_silent_result(value) is False

    def test_classifier_never_raises(self, watch_no_db):
        class Exploding:
            @property
            def content(self):
                raise RuntimeError("boom")
        # Must swallow and default to not-silent rather than break the server
        assert watch_no_db._is_silent_result(Exploding()) is False


class TestSilentDetection:
    """Silent failures flow through stats, health, buffers and DB."""

    def test_wrap_sync_silent(self, watch):
        def empty_tool():
            return ""
        wrapped = watch._wrap("empty", empty_tool)
        assert wrapped() == ""
        assert watch._total_silent == 1
        assert watch._total_errors == 0
        assert watch._stats["empty"].silent_count == 1
        assert watch._stats["empty"].error_count == 0

    def test_wrap_sync_non_silent(self, watch):
        def good_tool():
            return "data"
        wrapped = watch._wrap("good", good_tool)
        wrapped()
        assert watch._total_silent == 0
        assert watch._stats["good"].silent_count == 0

    def test_wrap_async_silent(self, watch):
        async def empty_async():
            return None
        wrapped = watch._wrap("empty_async", empty_async)
        assert asyncio.run(wrapped()) is None
        assert watch._total_silent == 1
        assert watch._stats["empty_async"].silent_count == 1

    def test_silent_not_counted_as_error(self, watch):
        watch._record("t", 10.0, "silent", None)
        assert watch._total_silent == 1
        assert watch._total_errors == 0
        assert len(watch._recent_errors) == 0
        assert len(watch._recent_silent) == 1

    def test_recent_silent(self, watch):
        watch._record("t", 10.0, "silent", None)
        watch._record("t", 12.0, "silent", None)
        silent = watch.recent_silent()
        assert len(silent) == 2
        assert silent[0]["status"] == "silent"

    def test_health_reports_silent(self, watch):
        for _ in range(8):
            watch._record("t", 10.0, "success", None)
        for _ in range(2):
            watch._record("t", 10.0, "silent", None)
        h = watch.health()
        assert h["total_silent"] == 2
        assert h["silent_rate"] == 0.2
        assert h["status"] == "degraded"  # 2/10 > 0.1

    def test_health_unhealthy_on_high_silent_rate(self, watch):
        for _ in range(6):
            watch._record("t", 10.0, "silent", None)
        for _ in range(4):
            watch._record("t", 10.0, "success", None)
        assert watch.health()["status"] == "unhealthy"  # 6/10 > 0.5

    def test_db_silent_failures(self, watch):
        watch._record("t", 10.0, "silent", None)
        watch._record("t", 10.0, "success", None)
        rows = watch.db_silent_failures()
        assert len(rows) == 1
        assert rows[0]["tool_name"] == "t"

    def test_db_tool_stats_includes_silent(self, watch):
        watch._record("t", 10.0, "silent", None)
        watch._record("t", 10.0, "success", None)
        stats = watch.db_tool_stats(hours=1)
        assert stats[0]["silent_count"] == 1

    def test_reset_clears_silent(self, watch):
        watch._record("t", 10.0, "silent", None)
        watch.reset()
        assert watch._total_silent == 0
        assert len(watch._recent_silent) == 0

    def test_stats_to_dict_has_silent(self, watch):
        watch._record("t", 10.0, "silent", None)
        d = watch._stats["t"].to_dict()
        assert d["silent_count"] == 1
        assert d["silent_rate"] == 1.0


class TestLowLevelSilentDetection:
    """Low-level Server: empty content with no error -> silent."""

    def _build_server(self, handler_fn):
        from mcp.server.lowlevel import Server
        server = Server("low-level-silent")

        @server.call_tool()
        async def call_tool(name: str, arguments: dict):
            return await handler_fn(name, arguments)

        return server

    def _make_request(self, tool_name, arguments=None):
        from mcp.types import CallToolRequest, CallToolRequestParams
        return CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=tool_name, arguments=arguments or {}),
        )

    def test_empty_content_is_silent(self, tmp_db):
        from mcp.types import CallToolRequest

        async def returns_empty(name, arguments):
            return []

        server = self._build_server(returns_empty)
        watch = instrument(server, db_path=tmp_db.path)
        handler = server.request_handlers[CallToolRequest]
        asyncio.run(handler(self._make_request("empty")))

        assert watch._total_silent == 1
        assert watch._total_errors == 0
        assert watch._stats["empty"].silent_count == 1

    def test_real_content_is_success(self, tmp_db):
        from mcp.types import CallToolRequest

        async def returns_data(name, arguments):
            return [{"type": "text", "text": "result"}]

        server = self._build_server(returns_data)
        watch = instrument(server, db_path=tmp_db.path)
        handler = server.request_handlers[CallToolRequest]
        asyncio.run(handler(self._make_request("good")))

        assert watch._total_silent == 0
        assert watch._stats["good"].call_count == 1


# ── Error buffer limit test ──────────────────────────────────────

class TestErrorBuffer:
    def test_error_buffer_capped_at_100(self, watch_no_db):
        for i in range(150):
            watch_no_db._record("tool", 10.0, "error", f"err-{i}")
        assert len(watch_no_db._recent_errors) == 100
        # Should keep the latest 100
        assert watch_no_db._recent_errors[0].error == "err-50"
        assert watch_no_db._recent_errors[-1].error == "err-149"
