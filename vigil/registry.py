"""
Vigil Tool Registry — Decorator-based tool registration with frame filtering.

Register tools with @tool(), tag them with frames, and let the registry
handle filtering based on the active context. Agents in "backend" mode
see backend tools, not creative tools — saving 50K+ tokens per session.
"""

from typing import Callable, Dict, Any, Awaitable, Optional
from functools import wraps


# Global tool storage
_tools: Dict[str, dict] = {}


def tool(
    name: str,
    description: str,
    input_schema: dict = None,
    properties: dict = None,
    required: list = None,
    frames: list = None,
):
    """
    Decorator to register a tool with optional frame tags.

    Args:
        name: Unique tool name
        description: Tool description (shown to LLM)
        input_schema: Full JSON Schema for inputs
        properties: Shorthand — dict of property definitions
        required: Shorthand — list of required property names
        frames: List of frame IDs where this tool is visible.
                None = visible in all frames. Include "core" to make
                a tool always visible regardless of active frame.

    Usage:
        @tool(
            name="deploy",
            description="Deploy to production",
            properties={"service": {"type": "string"}},
            required=["service"],
            frames=["backend", "devops"]
        )
        async def deploy_tool(args: dict) -> dict:
            ...
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        }

    def decorator(func: Callable[[dict], Awaitable[dict]]):
        _tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": func,
            "frames": frames,
        }

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def get_tools(frame: Optional[str] = None) -> dict:
    """
    Get tool definitions, optionally filtered by frame.

    Args:
        frame: If set, only return tools tagged for this frame + core tools.
               None returns all tools.

    Returns:
        {"tools": [list of tool definitions]}
    """
    tools = []
    for t in _tools.values():
        # Frame filtering: only when a frame is requested
        if frame and t.get("frames"):
            if frame not in t["frames"] and "core" not in t["frames"]:
                continue
        # frames=None on tool → available in all frames
        tools.append({
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
        })

    tools.sort(key=lambda x: x["name"])
    return {"tools": tools}


async def call_tool(name: str, args: dict) -> dict:
    """
    Execute a tool by name.

    Args:
        name: Tool name
        args: Tool arguments

    Returns:
        Tool result dict

    Raises:
        ValueError: Unknown tool
    """
    if name not in _tools:
        raise ValueError(f"Unknown tool: {name}")
    return await _tools[name]["handler"](args)


def list_registered() -> list[str]:
    """Get all registered tool names."""
    return sorted(_tools.keys())


def clear():
    """Clear all registered tools (for testing)."""
    _tools.clear()


def tool_count(frame: Optional[str] = None) -> int:
    """Count tools visible in a given frame."""
    return len(get_tools(frame=frame)["tools"])


# Helpers for tool responses
def text_result(text: str) -> dict:
    """Standard text content result."""
    return {"content": [{"type": "text", "text": text}]}


def json_result(data: Any) -> dict:
    """JSON text content result."""
    import json
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}


def error_result(message: str) -> dict:
    """Error text content result."""
    return {"content": [{"type": "text", "text": f"Error: {message}"}]}
