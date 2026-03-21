"""Tests for the Vigil MCP server."""

import os
import json
import tempfile
import pytest
from vigil.db import VigilDB
from vigil.mcp_server import create_server


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def db_path(db):
    return str(db.path)


@pytest.fixture
def server(db_path):
    return create_server(db_path=db_path)


def _parse(result) -> dict | list:
    """Extract JSON from FastMCP call_tool result tuple."""
    content_list = result[0]  # (list[TextContent], dict)
    return json.loads(content_list[0].text)


class TestServerCreation:
    def test_creates_server(self, server):
        assert server is not None
        assert server.name == "vigil"

    def test_custom_name(self, db_path):
        s = create_server(db_path=db_path, name="my-vigil")
        assert s.name == "my-vigil"

    def test_tools_registered(self, server):
        """Verify all expected tools are registered."""
        tools = server._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        expected = {
            "vigil_boot",
            "vigil_compile",
            "vigil_signal",
            "vigil_status",
            "vigil_signals",
            "vigil_handoff",
            "vigil_resume",
            "vigil_chain",
            "vigil_stale",
            "vigil_focus",
            "vigil_frames",
            "vigil_agents",
        }
        assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


class TestVigilBoot:
    @pytest.mark.anyio
    async def test_boot_empty(self, server):
        result = await server.call_tool("vigil_boot", {})
        data = _parse(result)
        assert "frame" in data
        assert data["frame"] == "default"

    @pytest.mark.anyio
    async def test_boot_after_compile(self, server):
        # Emit a signal, compile, then boot
        await server.call_tool("vigil_signal", {"agent": "test-agent", "content": "deployed auth v2"})
        await server.call_tool("vigil_compile", {})
        result = await server.call_tool("vigil_boot", {})
        data = _parse(result)
        assert data["frame"] is not None


class TestVigilSignal:
    @pytest.mark.anyio
    async def test_emit_signal(self, server):
        result = await server.call_tool("vigil_signal", {
            "agent": "test-agent",
            "content": "hello from test",
        })
        data = _parse(result)
        assert data["signal_id"] >= 1
        assert data["type"] == "observation"
        assert data["chars"] == len("hello from test")

    @pytest.mark.anyio
    async def test_signal_types(self, server):
        for stype in ["observation", "handoff", "summary", "alert"]:
            result = await server.call_tool("vigil_signal", {
                "agent": "test",
                "content": f"test {stype}",
                "signal_type": stype,
            })
            data = _parse(result)
            assert data["type"] == stype

    @pytest.mark.anyio
    async def test_directed_signal(self, server):
        result = await server.call_tool("vigil_signal", {
            "agent": "agent-a",
            "content": "hey agent-b",
            "to_agent": "agent-b",
        })
        data = _parse(result)
        assert data["signal_id"] >= 1


class TestVigilStatus:
    @pytest.mark.anyio
    async def test_status_empty(self, server):
        result = await server.call_tool("vigil_status", {})
        data = _parse(result)
        assert data["status"] == "empty"

    @pytest.mark.anyio
    async def test_status_after_compile(self, server):
        await server.call_tool("vigil_signal", {"agent": "test", "content": "something happened"})
        await server.call_tool("vigil_compile", {})
        result = await server.call_tool("vigil_status", {})
        data = _parse(result)
        assert "summary" in data
        assert len(data["summary"]) > 0


class TestVigilSignals:
    @pytest.mark.anyio
    async def test_read_signals(self, server):
        await server.call_tool("vigil_signal", {"agent": "a", "content": "msg 1"})
        await server.call_tool("vigil_signal", {"agent": "b", "content": "msg 2"})
        result = await server.call_tool("vigil_signals", {"hours": 1})
        data = _parse(result)
        assert len(data) == 2

    @pytest.mark.anyio
    async def test_filter_by_agent(self, server):
        await server.call_tool("vigil_signal", {"agent": "a", "content": "from a"})
        await server.call_tool("vigil_signal", {"agent": "b", "content": "from b"})
        result = await server.call_tool("vigil_signals", {"agent": "a"})
        data = _parse(result)
        assert len(data) == 1
        assert data[0]["from_agent"] == "a"


class TestVigilHandoff:
    @pytest.mark.anyio
    async def test_handoff(self, server):
        result = await server.call_tool("vigil_handoff", {
            "agent": "test-agent",
            "summary": "Built the MCP server module",
            "next_steps": "Write tests, wire into CLI",
        })
        data = _parse(result)
        assert data["status"] == "handed_off"
        assert data["handoff_id"] >= 1

    @pytest.mark.anyio
    async def test_handoff_with_files(self, server):
        result = await server.call_tool("vigil_handoff", {
            "agent": "coder",
            "summary": "Refactored auth module",
            "files_touched": "auth.py, middleware.py, tests/test_auth.py",
            "decisions": "Switched from JWT to session tokens",
        })
        data = _parse(result)
        assert data["status"] == "handed_off"


class TestVigilResume:
    @pytest.mark.anyio
    async def test_resume_empty(self, server):
        result = await server.call_tool("vigil_resume", {})
        data = _parse(result)
        assert data["last_handoff"] is None
        assert "resuming_as" in data

    @pytest.mark.anyio
    async def test_resume_after_handoff(self, server):
        # Create a handoff via MCP (uses HandoffProtocol)
        await server.call_tool("vigil_handoff", {
            "agent": "agent-1",
            "summary": "finished phase 1",
            "next_steps": "start phase 2",
        })
        # Resume
        result = await server.call_tool("vigil_resume", {"agent": "agent-1"})
        data = _parse(result)
        assert data["last_handoff"] is not None
        assert data["last_handoff"]["agent_id"] == "agent-1"
        assert "finished phase 1" in data["last_handoff"]["summary"]
        # signals_since_handoff should be a list, not an int
        assert isinstance(data["signals_since_handoff"], list)


class TestVigilChain:
    @pytest.mark.anyio
    async def test_chain_empty(self, server):
        result = await server.call_tool("vigil_chain", {})
        text = result[0][0].text
        assert "No previous handoffs" in text

    @pytest.mark.anyio
    async def test_chain_after_handoffs(self, server):
        await server.call_tool("vigil_handoff", {"agent": "a", "summary": "did thing 1"})
        await server.call_tool("vigil_handoff", {"agent": "b", "summary": "did thing 2"})
        result = await server.call_tool("vigil_chain", {"limit": 2})
        text = result[0][0].text
        assert "did thing 1" in text
        assert "did thing 2" in text


class TestVigilStale:
    @pytest.mark.anyio
    async def test_stale_empty(self, server):
        result = await server.call_tool("vigil_stale", {})
        data = _parse(result)
        assert data["stale_sessions"] == []


class TestVigilSignalValidation:
    @pytest.mark.anyio
    async def test_invalid_signal_type(self, server):
        result = await server.call_tool("vigil_signal", {
            "agent": "test",
            "content": "hello",
            "signal_type": "bogus",
        })
        data = _parse(result)
        assert "error" in data
        assert "bogus" in data["error"]


class TestVigilFocus:
    @pytest.mark.anyio
    async def test_list_empty(self, server):
        result = await server.call_tool("vigil_focus", {"action": "list"})
        data = _parse(result)
        assert data == []

    @pytest.mark.anyio
    async def test_add_and_list(self, server):
        await server.call_tool("vigil_focus", {
            "action": "add",
            "description": "Ship MCP server",
            "priority": 1,
        })
        await server.call_tool("vigil_focus", {
            "action": "add",
            "description": "Write docs",
            "priority": 3,
        })
        result = await server.call_tool("vigil_focus", {"action": "list"})
        data = _parse(result)
        assert len(data) == 2
        assert data[0]["priority"] == 1  # sorted by priority

    @pytest.mark.anyio
    async def test_complete(self, server):
        add_result = await server.call_tool("vigil_focus", {
            "action": "add",
            "description": "test task",
        })
        focus_id = _parse(add_result)["focus_id"]
        await server.call_tool("vigil_focus", {
            "action": "complete",
            "focus_id": focus_id,
        })
        result = await server.call_tool("vigil_focus", {"action": "list"})
        data = _parse(result)
        assert len(data) == 0

    @pytest.mark.anyio
    async def test_add_requires_description(self, server):
        result = await server.call_tool("vigil_focus", {"action": "add"})
        data = _parse(result)
        assert "error" in data


class TestVigilFrames:
    @pytest.mark.anyio
    async def test_list_frames(self, server):
        result = await server.call_tool("vigil_frames", {"action": "list"})
        data = _parse(result)
        assert isinstance(data, list)

    @pytest.mark.anyio
    async def test_register_frame(self, server):
        await server.call_tool("vigil_frames", {
            "action": "register",
            "frame_id": "backend",
            "description": "Backend development",
            "triggers": "api, database, deploy, server",
        })
        result = await server.call_tool("vigil_frames", {"action": "list"})
        data = _parse(result)
        frame_ids = [f["id"] for f in data]
        assert "backend" in frame_ids


class TestVigilAgents:
    @pytest.mark.anyio
    async def test_agents_empty(self, server):
        result = await server.call_tool("vigil_agents", {})
        data = _parse(result)
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_agents_after_signals(self, server):
        await server.call_tool("vigil_signal", {"agent": "alpha", "content": "hello"})
        await server.call_tool("vigil_signal", {"agent": "beta", "content": "world"})
        await server.call_tool("vigil_signal", {"agent": "alpha", "content": "again"})
        result = await server.call_tool("vigil_agents", {})
        data = _parse(result)
        assert data["total"] == 2
        # Alpha should have 2 signals
        alpha = next(a for a in data["agents"] if a["from_agent"] == "alpha")
        assert alpha["signal_count"] == 2

    @pytest.mark.anyio
    async def test_single_agent_detail(self, server):
        await server.call_tool("vigil_signal", {"agent": "gamma", "content": "test"})
        result = await server.call_tool("vigil_agents", {"agent": "gamma"})
        data = _parse(result)
        assert data["agent"]["from_agent"] == "gamma"
