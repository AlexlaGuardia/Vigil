"""
Vigil Quickstart — Multi-agent project with cross-session awareness.

This example shows:
1. Setting up frames for different work contexts
2. Registering tools with frame tags
3. Running the daemon to compile awareness
4. Agents emitting signals and booting with hot context
"""

import asyncio
import time
from vigil import VigilDB, SignalBus, FrameDetector, AwarenessCompiler, VigilDaemon
from vigil.registry import tool, get_tools, call_tool, tool_count


# -- Step 1: Initialize --
db = VigilDB("quickstart.db")
bus = SignalBus(db)
frames = FrameDetector(db)
compiler = AwarenessCompiler(db, frame_detector=frames)

# -- Step 2: Register frames --
frames.register("backend", "API and database work", ["api", "database", "endpoint", "deploy"])
frames.register("frontend", "UI and component work", ["react", "component", "css", "layout"])
frames.register("creative", "Writing and design", ["story", "character", "lore", "chapter"])

# -- Step 3: Register tools with frame tags --
@tool(name="health", description="System health check", frames=["core"])
async def health(args):
    return {"content": [{"type": "text", "text": "All systems operational"}]}

@tool(name="deploy", description="Deploy to production", frames=["backend"],
      properties={"service": {"type": "string"}}, required=["service"])
async def deploy(args):
    return {"content": [{"type": "text", "text": f"Deployed {args['service']}"}]}

@tool(name="query_db", description="Run a database query", frames=["backend"],
      properties={"sql": {"type": "string"}}, required=["sql"])
async def query_db(args):
    return {"content": [{"type": "text", "text": f"Query result for: {args['sql']}"}]}

@tool(name="render_component", description="Render a React component", frames=["frontend"],
      properties={"name": {"type": "string"}}, required=["name"])
async def render_component(args):
    return {"content": [{"type": "text", "text": f"Rendered <{args['name']} />"}]}

@tool(name="write_chapter", description="Write a story chapter", frames=["creative"],
      properties={"title": {"type": "string"}}, required=["title"])
async def write_chapter(args):
    return {"content": [{"type": "text", "text": f"Chapter: {args['title']}"}]}


def main():
    # -- Show frame filtering --
    print("=== Frame Filtering ===")
    print(f"All tools:      {tool_count()}")
    print(f"Backend frame:  {tool_count('backend')}")
    print(f"Frontend frame: {tool_count('frontend')}")
    print(f"Creative frame: {tool_count('creative')}")
    print()

    # Backend sees: health (core) + deploy + query_db = 3
    # Frontend sees: health (core) + render_component = 2
    # Creative sees: health (core) + write_chapter = 2

    # -- Simulate agent work --
    print("=== Agent Signals ===")
    bus.emit("backend-agent", "Deployed new API endpoint for /users")
    bus.emit("backend-agent", "Database migration completed successfully")
    bus.emit("frontend-agent", "Updated the dashboard layout component")
    print("3 signals emitted")
    print()

    # -- Compile awareness --
    print("=== Awareness Compilation ===")
    compiler.synthesize()
    context = compiler.compile()
    print(f"Frame detected: {context['frame']}")
    print(f"Recent signals: {context['recent_signals']}")
    print(f"Awareness: {context['awareness'][:100]}...")
    print()

    # -- Boot (what an agent sees on startup) --
    print("=== Agent Boot ===")
    boot_context = compiler.boot()
    print(f"Frame: {boot_context.get('frame')}")
    print(f"Focus: {len(boot_context.get('focus', []))} items")
    print(f"Ready to work in <1 second")
    print()

    # -- Add focus items --
    print("=== Focus Queue ===")
    db.add_focus("Ship user authentication", priority=1, owner="backend")
    db.add_focus("Responsive dashboard layout", priority=2, owner="frontend")
    db.add_focus("Chapter 3 draft", priority=3, owner="creative")

    for item in db.get_active_focus():
        print(f"  [P{item['priority']}] {item['description']} ({item.get('owner', 'unassigned')})")
    print()

    # -- Run a tool --
    print("=== Tool Execution ===")
    result = asyncio.run(call_tool("deploy", {"service": "api-v2"}))
    print(f"Result: {result['content'][0]['text']}")

    # Cleanup
    import os
    os.unlink("quickstart.db")
    print("\nDone! Run `vigil init && vigil daemon start` to try it for real.")


if __name__ == "__main__":
    main()
