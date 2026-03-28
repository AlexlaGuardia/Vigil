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


# ── Error buffer limit test ──────────────────────────────────────

class TestErrorBuffer:
    def test_error_buffer_capped_at_100(self, watch_no_db):
        for i in range(150):
            watch_no_db._record("tool", 10.0, "error", f"err-{i}")
        assert len(watch_no_db._recent_errors) == 100
        # Should keep the latest 100
        assert watch_no_db._recent_errors[0].error == "err-50"
        assert watch_no_db._recent_errors[-1].error == "err-149"
