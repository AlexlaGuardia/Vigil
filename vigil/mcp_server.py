"""
Vigil MCP Server — Expose Vigil as an MCP tool server.

Any MCP-compatible client (Claude Code, Claude Desktop, Cursor, Windsurf)
can connect and give their agents persistent awareness, signal coordination,
and frame-based tool filtering.

Usage:
    # stdio (Claude Code / Claude Desktop)
    vigil serve

    # SSE (remote clients)
    vigil serve --transport sse --port 8300

    # Programmatic
    from vigil.mcp_server import create_server
    mcp = create_server("vigil.db")
    mcp.run()
"""

import json
import os
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from vigil.db import VigilDB
from vigil.signals import SignalBus
from vigil.frames import FrameDetector
from vigil.awareness import AwarenessCompiler


def _fmt(data: Any) -> str:
    """Format response data as indented JSON string."""
    return json.dumps(data, indent=2, default=str)


def create_server(
    db_path: str = "vigil.db",
    default_frame: str = "default",
    name: str = "vigil",
) -> FastMCP:
    """
    Create a Vigil MCP server instance.

    Args:
        db_path: Path to Vigil SQLite database
        default_frame: Default frame when no triggers match
        name: Server name for MCP discovery

    Returns:
        Configured FastMCP instance with all Vigil tools registered
    """
    mcp = FastMCP(
        name,
        instructions=(
            "Cognitive infrastructure for AI agents. "
            "Provides awareness daemon, signal coordination, "
            "frame-based tool filtering, and session handoff. "
            "Use vigil_boot on startup to load hot context."
        ),
    )

    # Lazy-init singletons — created on first tool call
    _state: dict = {}

    def _get_db() -> VigilDB:
        if "db" not in _state:
            _state["db"] = VigilDB(db_path)
        return _state["db"]

    def _get_bus() -> SignalBus:
        if "bus" not in _state:
            _state["bus"] = SignalBus(_get_db())
        return _state["bus"]

    def _get_frames() -> FrameDetector:
        if "frames" not in _state:
            _state["frames"] = FrameDetector(_get_db(), default_frame=default_frame)
        return _state["frames"]

    def _get_compiler() -> AwarenessCompiler:
        if "compiler" not in _state:
            _state["compiler"] = AwarenessCompiler(_get_db(), frame_detector=_get_frames())
        return _state["compiler"]

    # ── Tools ─────────────────────────────────────────────────────

    @mcp.tool()
    async def vigil_boot() -> str:
        """Boot with pre-compiled hot context. Call this first in every session.

        Returns the current frame, awareness summary, active focus items,
        and recent signal count. Instant — no recompilation needed."""
        compiler = _get_compiler()
        context = compiler.boot()
        return _fmt(context)

    @mcp.tool()
    async def vigil_compile() -> str:
        """Force a fresh awareness compilation cycle.

        Synthesizes unacknowledged signals into awareness, detects the
        active frame, and builds new hot context. Usually the daemon
        handles this automatically — use this for manual refresh."""
        compiler = _get_compiler()
        compiler.synthesize()
        context = compiler.compile()
        return _fmt(context)

    @mcp.tool()
    async def vigil_signal(
        agent: str,
        content: str,
        signal_type: str = "observation",
        to_agent: str = "",
    ) -> str:
        """Emit a signal from an agent.

        Signals are short messages that the daemon synthesizes into awareness.
        Content is auto-truncated to the type's budget.

        Args:
            agent: Agent identifier (e.g. "backend-agent", "claude-code")
            content: Signal content (observation: 400 chars, handoff: 600, summary: 800, alert: 300)
            signal_type: One of: observation, handoff, summary, alert
            to_agent: Optional target agent for directed signals
        """
        bus = _get_bus()
        sig = bus.emit(
            from_agent=agent,
            content=content,
            signal_type=signal_type,
            to_agent=to_agent or None,
        )
        # Auto-register agent on first signal
        _register_agent_if_new(agent, "mcp")
        return _fmt({
            "signal_id": sig.id,
            "type": sig.signal_type.value,
            "chars": len(sig.content),
            "budget": sig.signal_type.budget,
        })

    @mcp.tool()
    async def vigil_status() -> str:
        """Get current awareness state.

        Shows the compiled awareness summary, when it was last updated,
        and who updated it (daemon, compiler, or manual)."""
        db = _get_db()
        awareness = db.get_awareness()
        if not awareness or not awareness.get("summary"):
            return _fmt({"status": "empty", "message": "No awareness compiled yet. Run vigil_compile or start the daemon."})
        return _fmt({
            "summary": awareness["summary"],
            "updated_at": awareness.get("updated_at"),
            "updated_by": awareness.get("updated_by"),
        })

    @mcp.tool()
    async def vigil_signals(
        hours: int = 1,
        limit: int = 10,
        agent: str = "",
    ) -> str:
        """Read recent signals.

        Args:
            hours: Time window in hours (default: 1)
            limit: Max signals to return (default: 10)
            agent: Filter by agent name (optional)
        """
        bus = _get_bus()
        signals = bus.read(hours=hours, limit=limit)
        if agent:
            signals = [s for s in signals if s.from_agent == agent]
        return _fmt([s.to_dict() for s in signals])

    @mcp.tool()
    async def vigil_handoff(
        agent: str,
        summary: str,
        next_steps: str = "",
        files_touched: str = "",
        decisions: str = "",
    ) -> str:
        """End a session with a structured handoff.

        The next agent that boots will see this handoff context.
        Also emits a handoff signal automatically.

        Args:
            agent: Agent identifier
            summary: What happened this session
            next_steps: Comma-separated list of what to do next
            files_touched: Comma-separated list of files modified
            decisions: Comma-separated list of decisions made
        """
        db = _get_db()
        bus = _get_bus()

        # Find or create active session
        active = db.query_one(
            "SELECT id FROM sessions WHERE agent_id = ? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (agent,),
        )
        if active:
            session_id = active["id"]
        else:
            session_id = db.start_session(agent)

        # End the session
        db.end_session(session_id, summary=summary, next_steps=next_steps)

        # Store extended handoff data
        _store_handoff_data(db, session_id, files_touched, decisions)

        # Emit handoff signal
        handoff_content = summary[:400]
        if next_steps:
            remaining = 600 - len(handoff_content) - 8
            if remaining > 0:
                handoff_content += f" Next: {next_steps[:remaining]}"
        bus.emit(from_agent=agent, content=handoff_content, signal_type="handoff")

        return _fmt({
            "session_id": session_id,
            "status": "handed_off",
            "summary_chars": len(summary),
        })

    @mcp.tool()
    async def vigil_resume(agent: str = "") -> str:
        """Resume from the last session's handoff.

        Returns hot context + last handoff summary + any signals emitted
        since the handoff. If agent is specified, gets that agent's last
        handoff — otherwise gets the most recent across all agents.

        Args:
            agent: Agent to resume as (optional — defaults to most recent)
        """
        db = _get_db()
        compiler = _get_compiler()

        # Get hot context
        context = compiler.boot()

        # Get last completed session
        if agent:
            session = db.query_one(
                "SELECT id, agent_id, frame, summary, next_steps, started_at, ended_at "
                "FROM sessions WHERE agent_id = ? AND ended_at IS NOT NULL "
                "ORDER BY ended_at DESC LIMIT 1",
                (agent,),
            )
        else:
            session = db.query_one(
                "SELECT id, agent_id, frame, summary, next_steps, started_at, ended_at "
                "FROM sessions WHERE ended_at IS NOT NULL "
                "ORDER BY ended_at DESC LIMIT 1",
            )

        handoff = None
        if session:
            handoff = {
                "agent": session["agent_id"],
                "summary": session.get("summary", ""),
                "next_steps": session.get("next_steps", ""),
                "ended_at": session.get("ended_at"),
            }
            # Get extended handoff data if available
            extended = _get_handoff_data(db, session["id"])
            if extended:
                handoff.update(extended)

        # Count signals since handoff
        signals_since = 0
        if session and session.get("ended_at"):
            row = db.query_one(
                "SELECT COUNT(*) as cnt FROM signals WHERE created_at > ?",
                (session["ended_at"],),
            )
            if row:
                signals_since = row["cnt"]

        # Start a new session for this agent
        resume_agent = agent or (session["agent_id"] if session else "unknown")
        new_session = db.start_session(resume_agent, frame=context.get("frame"))

        return _fmt({
            "session_id": new_session,
            "context": context,
            "last_handoff": handoff,
            "signals_since_handoff": signals_since,
        })

    @mcp.tool()
    async def vigil_focus(
        action: str = "list",
        description: str = "",
        priority: int = 5,
        owner: str = "",
        focus_id: int = 0,
    ) -> str:
        """Manage the focus queue — priority-ordered work items.

        Args:
            action: "list" (default), "add", or "complete"
            description: Task description (required for "add")
            priority: Priority 1-10, lower = higher priority (default: 5)
            owner: Who owns this task (optional)
            focus_id: Focus item ID (required for "complete")
        """
        db = _get_db()

        if action == "list":
            items = db.get_active_focus(limit=10)
            return _fmt(items)

        elif action == "add":
            if not description:
                return _fmt({"error": "description is required for 'add' action"})
            fid = db.add_focus(description=description, priority=priority, owner=owner or None)
            return _fmt({"focus_id": fid, "priority": priority, "description": description})

        elif action == "complete":
            if not focus_id:
                return _fmt({"error": "focus_id is required for 'complete' action"})
            db.complete_focus(focus_id)
            return _fmt({"focus_id": focus_id, "status": "completed"})

        else:
            return _fmt({"error": f"Unknown action: {action}. Use list, add, or complete."})

    @mcp.tool()
    async def vigil_frames(action: str = "list", frame_id: str = "", description: str = "", triggers: str = "") -> str:
        """Manage context frames for tool filtering.

        Frames control which tools agents see, reducing token overhead.

        Args:
            action: "list" (default) or "register"
            frame_id: Frame identifier (required for "register")
            description: Frame description (for "register")
            triggers: Comma-separated trigger keywords (for "register")
        """
        db = _get_db()

        if action == "list":
            frames = db.get_frames()
            return _fmt(frames)

        elif action == "register":
            if not frame_id:
                return _fmt({"error": "frame_id is required for 'register' action"})
            trigger_list = [t.strip() for t in triggers.split(",") if t.strip()] if triggers else []
            db.register_frame(frame_id, description=description, triggers=trigger_list)
            return _fmt({"frame_id": frame_id, "triggers": trigger_list, "status": "registered"})

        else:
            return _fmt({"error": f"Unknown action: {action}. Use list or register."})

    @mcp.tool()
    async def vigil_agents(agent: str = "") -> str:
        """List known agents and their activity.

        Shows all agents that have emitted signals, with their last
        activity time and signal count. Optionally filter by agent name.

        Args:
            agent: Filter by agent name (optional)
        """
        db = _get_db()

        if agent:
            # Single agent detail
            row = db.query_one(
                "SELECT from_agent, COUNT(*) as signal_count, "
                "MAX(created_at) as last_seen, "
                "MIN(created_at) as first_seen "
                "FROM signals WHERE from_agent = ? GROUP BY from_agent",
                (agent,),
            )
            if not row:
                return _fmt({"error": f"No signals found from agent: {agent}"})

            sessions = db.query_all(
                "SELECT id, frame, summary, started_at, ended_at "
                "FROM sessions WHERE agent_id = ? ORDER BY started_at DESC LIMIT 5",
                (agent,),
            )
            return _fmt({"agent": row, "recent_sessions": sessions})

        else:
            # All agents summary
            agents = db.query_all(
                "SELECT from_agent, COUNT(*) as signal_count, "
                "MAX(created_at) as last_seen "
                "FROM signals GROUP BY from_agent ORDER BY last_seen DESC",
            )
            return _fmt({"agents": agents, "total": len(agents)})

    # ── Helpers ───────────────────────────────────────────────────

    def _register_agent_if_new(agent_id: str, agent_type: str = "unknown"):
        """Auto-register agent in the agents table if it exists."""
        db = _get_db()
        try:
            db.execute(
                "INSERT OR IGNORE INTO agents (id, name, type, last_seen, session_count) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0)",
                (agent_id, agent_id, agent_type),
            )
            db.execute(
                "UPDATE agents SET last_seen = CURRENT_TIMESTAMP WHERE id = ?",
                (agent_id,),
            )
        except Exception:
            # agents table may not exist yet (pre-integration)
            pass

    def _store_handoff_data(db: VigilDB, session_id: int, files_touched: str, decisions: str):
        """Store extended handoff data. Gracefully handles missing columns."""
        try:
            db.execute(
                "UPDATE sessions SET summary = summary || ? WHERE id = ?",
                ("", session_id),
            )
        except Exception:
            pass
        # Store as JSON in a handoff metadata signal if extended columns don't exist
        if files_touched or decisions:
            meta = {}
            if files_touched:
                meta["files_touched"] = [f.strip() for f in files_touched.split(",") if f.strip()]
            if decisions:
                meta["decisions"] = [d.strip() for d in decisions.split(",") if d.strip()]
            try:
                db.execute(
                    "INSERT INTO signals (from_agent, signal_type, content) VALUES (?, ?, ?)",
                    (f"_handoff_{session_id}", "observation", json.dumps(meta)[:400]),
                )
            except Exception:
                pass

    def _get_handoff_data(db: VigilDB, session_id: int) -> Optional[dict]:
        """Retrieve extended handoff data."""
        row = db.query_one(
            "SELECT content FROM signals WHERE from_agent = ? ORDER BY created_at DESC LIMIT 1",
            (f"_handoff_{session_id}",),
        )
        if row and row.get("content"):
            try:
                return json.loads(row["content"])
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    return mcp


# ── Entry points ──────────────────────────────────────────────────

def run_stdio(db_path: str = "vigil.db", default_frame: str = "default"):
    """Run the Vigil MCP server over stdio (for Claude Code / Claude Desktop)."""
    server = create_server(db_path=db_path, default_frame=default_frame)
    server.run(transport="stdio")


def run_sse(
    db_path: str = "vigil.db",
    default_frame: str = "default",
    host: str = "127.0.0.1",
    port: int = 8300,
):
    """Run the Vigil MCP server over SSE (for remote clients)."""
    server = create_server(db_path=db_path, default_frame=default_frame)
    server.settings.host = host
    server.settings.port = port
    server.run(transport="sse")


# Allow direct execution: python -m vigil.mcp_server
if __name__ == "__main__":
    import sys

    transport = "stdio"
    db = os.environ.get("VIGIL_DB", "vigil.db")

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--sse":
            transport = "sse"
        elif arg == "--db" and i < len(sys.argv) - 1:
            db = sys.argv[i + 1]

    if transport == "sse":
        run_sse(db_path=db)
    else:
        run_stdio(db_path=db)
