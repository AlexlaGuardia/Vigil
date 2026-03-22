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
from typing import Any

from mcp.server.fastmcp import FastMCP

from vigil.db import VigilDB
from vigil.signals import SignalBus, SignalType
from vigil.frames import FrameDetector
from vigil.awareness import AwarenessCompiler
from vigil.handoff import HandoffProtocol
from vigil.triggers import TriggerEngine
from vigil.knowledge import KnowledgeBase


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

    def _get_handoff() -> HandoffProtocol:
        if "handoff" not in _state:
            _state["handoff"] = HandoffProtocol(_get_db())
        return _state["handoff"]

    def _get_triggers() -> TriggerEngine:
        if "triggers" not in _state:
            _state["triggers"] = TriggerEngine(_get_db(), _get_bus())
        return _state["triggers"]

    def _get_knowledge() -> KnowledgeBase:
        if "knowledge" not in _state:
            _state["knowledge"] = KnowledgeBase(_get_db())
        return _state["knowledge"]

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
        try:
            sig = bus.emit(
                from_agent=agent,
                content=content,
                signal_type=signal_type,
                to_agent=to_agent or None,
            )
        except ValueError:
            valid = ", ".join(t.value for t in SignalType)
            return _fmt({"error": f"Invalid signal_type: '{signal_type}'. Valid types: {valid}"})
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
        proto = _get_handoff()

        files_list = [f.strip() for f in files_touched.split(",") if f.strip()] if files_touched else []
        decisions_list = [d.strip() for d in decisions.split(",") if d.strip()] if decisions else []
        steps_list = [s.strip() for s in next_steps.split(",") if s.strip()] if next_steps else []

        handoff = proto.end_session(
            agent_id=agent,
            summary=summary,
            files_touched=files_list,
            decisions=decisions_list,
            next_steps=steps_list,
        )

        return _fmt({
            "handoff_id": handoff.id,
            "status": "handed_off",
            "summary_chars": len(summary),
        })

    @mcp.tool()
    async def vigil_resume(agent: str = "") -> str:
        """Resume from the last session's handoff.

        Returns hot context + last handoff summary + signals emitted
        since the handoff + pending next steps from recent handoffs.

        Args:
            agent: Agent to resume as (optional — defaults to most recent)
        """
        proto = _get_handoff()
        resume_agent = agent or "unknown"
        context = proto.resume(resume_agent)

        # Serialize the last_handoff Handoff dict consistently
        last = context.get("last_handoff")
        if last and "agent_id" in last:
            # Already a dict from HandoffProtocol — good
            pass

        return _fmt(context)

    @mcp.tool()
    async def vigil_chain(limit: int = 3) -> str:
        """Get a briefing of the last N handoffs across all agents.

        Compressed view of recent session activity — useful for
        understanding what happened while you were away.

        Args:
            limit: Number of recent handoffs to include (default: 3)
        """
        proto = _get_handoff()
        return proto.get_handoff_chain(limit=limit)

    @mcp.tool()
    async def vigil_stale(minutes: int = 30) -> str:
        """Find agents with open sessions that have gone silent.

        Detects sessions where no signals have been emitted for N minutes.
        Useful for daemon cleanup or alerting.

        Args:
            minutes: Silence threshold in minutes (default: 30)
        """
        proto = _get_handoff()
        stale = proto.auto_detect_stale(minutes=minutes)
        return _fmt({"stale_sessions": stale, "threshold_minutes": minutes})

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
    async def vigil_triggers(
        action: str = "list",
        name: str = "",
        action_type: str = "log",
        signal_type: str = "",
        agent_pattern: str = "*",
        content_pattern: str = "",
        action_config: str = "{}",
    ) -> str:
        """Manage event triggers — pattern-matching rules that fire actions on signals.

        Args:
            action: "list" (default), "add", or "remove"
            name: Trigger name (required for add/remove)
            action_type: One of: webhook, signal, focus, log (for "add")
            signal_type: Filter to this signal type, empty = all (for "add")
            agent_pattern: Glob pattern for agent names, * = all (for "add")
            content_pattern: Regex pattern for signal content (for "add")
            action_config: JSON string of action config (for "add")
        """
        engine = _get_triggers()

        if action == "list":
            triggers = engine.list_triggers(enabled_only=False)
            return _fmt([t.to_dict() for t in triggers])

        elif action == "add":
            if not name:
                return _fmt({"error": "name is required for 'add' action"})
            try:
                config = json.loads(action_config) if action_config else {}
            except json.JSONDecodeError:
                return _fmt({"error": f"Invalid action_config JSON: {action_config}"})
            t = engine.register(
                name=name,
                action_type=action_type,
                action_config=config,
                signal_type=signal_type or None,
                agent_pattern=agent_pattern,
                content_pattern=content_pattern or None,
            )
            return _fmt(t.to_dict())

        elif action == "remove":
            if not name:
                return _fmt({"error": "name is required for 'remove' action"})
            engine.remove(name)
            return _fmt({"name": name, "status": "removed"})

        else:
            return _fmt({"error": f"Unknown action: {action}. Use list, add, or remove."})

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

    @mcp.tool()
    async def vigil_know(
        key: str,
        value: str,
        category: str = "general",
        agent: str = "",
        confidence: float = 1.0,
    ) -> str:
        """Store or update a knowledge entry.

        Knowledge is persistent — it survives signal compaction and
        accumulates over time. Use for learned patterns, decisions,
        and facts that agents should remember long-term.

        Args:
            key: Unique identifier (e.g. "deploy_branch", "db_engine")
            value: The knowledge content
            category: Category for grouping (e.g. "config", "pattern", "decision")
            agent: Which agent is storing this (optional)
            confidence: Confidence level 0.0-1.0 (default: 1.0)
        """
        kb = _get_knowledge()
        entry = kb.set(
            key=key,
            value=value,
            category=category,
            source_agent=agent or None,
            confidence=confidence,
        )
        if agent:
            _register_agent_if_new(agent, "mcp")
        return _fmt(entry.to_dict())

    @mcp.tool()
    async def vigil_recall(
        query: str,
        category: str = "",
        limit: int = 10,
    ) -> str:
        """Search knowledge by fuzzy matching on key, value, and category.

        Returns entries ranked by relevance (key matches first).

        Args:
            query: Search terms (matches against key, value, and category)
            category: Filter to a specific category (optional)
            limit: Max results (default: 10)
        """
        kb = _get_knowledge()
        results = kb.recall(query, category=category or None, limit=limit)
        return _fmt([e.to_dict() for e in results])

    @mcp.tool()
    async def vigil_knowledge(
        action: str = "list",
        key: str = "",
        category: str = "",
        limit: int = 50,
    ) -> str:
        """Manage the knowledge base.

        Args:
            action: "list" (default), "get", "delete", or "categories"
            key: Knowledge key (required for "get" and "delete")
            category: Filter by category (for "list")
            limit: Max entries to return (for "list", default: 50)
        """
        kb = _get_knowledge()

        if action == "list":
            entries = kb.list(category=category or None, limit=limit)
            return _fmt({
                "entries": [e.to_dict() for e in entries],
                "total": kb.count(category=category or None),
            })

        elif action == "get":
            if not key:
                return _fmt({"error": "key is required for 'get' action"})
            entry = kb.get(key)
            if not entry:
                return _fmt({"error": f"No knowledge entry with key: {key}"})
            return _fmt(entry.to_dict())

        elif action == "delete":
            if not key:
                return _fmt({"error": "key is required for 'delete' action"})
            deleted = kb.delete(key)
            if not deleted:
                return _fmt({"error": f"No knowledge entry with key: {key}"})
            return _fmt({"key": key, "status": "deleted"})

        elif action == "categories":
            cats = kb.categories()
            return _fmt({"categories": cats, "total": len(cats)})

        else:
            return _fmt({"error": f"Unknown action: {action}. Use list, get, delete, or categories."})

    # ── Helpers ───────────────────────────────────────────────────

    def _register_agent_if_new(agent_id: str, agent_type: str = "unknown"):
        """Auto-register agent in the agents table."""
        db = _get_db()
        db.execute(
            "INSERT OR IGNORE INTO agents (id, name, type, last_seen, session_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0)",
            (agent_id, agent_id, agent_type),
        )
        db.execute(
            "UPDATE agents SET last_seen = CURRENT_TIMESTAMP WHERE id = ?",
            (agent_id,),
        )

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
