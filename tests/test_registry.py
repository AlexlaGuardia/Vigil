"""Tests for tool registry and frame filtering."""

import pytest
from vigil.registry import tool, get_tools, call_tool, clear, tool_count


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before each test."""
    clear()
    yield
    clear()


class TestToolRegistration:
    def test_register_basic(self):
        @tool(name="test_tool", description="A test tool")
        async def test_tool(args):
            return {"content": [{"type": "text", "text": "ok"}]}

        tools = get_tools()
        assert len(tools["tools"]) == 1
        assert tools["tools"][0]["name"] == "test_tool"

    def test_register_with_schema(self):
        @tool(
            name="greet",
            description="Greet someone",
            properties={"name": {"type": "string"}},
            required=["name"],
        )
        async def greet(args):
            return {"content": [{"type": "text", "text": f"Hello {args['name']}"}]}

        tools = get_tools()
        schema = tools["tools"][0]["inputSchema"]
        assert "name" in schema["properties"]
        assert "name" in schema["required"]


class TestFrameFiltering:
    def test_no_frame_returns_all(self):
        @tool(name="a", description="A", frames=["backend"])
        async def a(args): pass

        @tool(name="b", description="B", frames=["frontend"])
        async def b(args): pass

        assert tool_count() == 2

    def test_frame_filters(self):
        @tool(name="api", description="API", frames=["backend"])
        async def api(args): pass

        @tool(name="ui", description="UI", frames=["frontend"])
        async def ui(args): pass

        assert tool_count(frame="backend") == 1
        assert tool_count(frame="frontend") == 1

    def test_core_always_visible(self):
        @tool(name="health", description="Health check", frames=["core"])
        async def health(args): pass

        @tool(name="api", description="API", frames=["backend"])
        async def api(args): pass

        # Core tools visible in every frame
        assert tool_count(frame="backend") == 2
        assert tool_count(frame="frontend") == 1  # Only core

    def test_no_frames_means_all(self):
        @tool(name="universal", description="Available everywhere")
        async def universal(args): pass

        @tool(name="scoped", description="Only backend", frames=["backend"])
        async def scoped(args): pass

        assert tool_count(frame="backend") == 2
        assert tool_count(frame="frontend") == 1  # Only universal

    def test_multi_frame_tool(self):
        @tool(name="deploy", description="Deploy", frames=["backend", "devops"])
        async def deploy(args): pass

        assert tool_count(frame="backend") == 1
        assert tool_count(frame="devops") == 1
        assert tool_count(frame="frontend") == 0


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_call_tool(self):
        @tool(name="echo", description="Echo input", properties={"msg": {"type": "string"}})
        async def echo(args):
            return {"content": [{"type": "text", "text": args["msg"]}]}

        result = await call_tool("echo", {"msg": "hello"})
        assert result["content"][0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            await call_tool("nonexistent", {})
