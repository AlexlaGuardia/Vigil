"""
Vigil CLI — Command-line interface for managing the daemon and signals.

Usage:
    vigil init                    Initialize a new Vigil project
    vigil quickstart              Interactive setup wizard
    vigil daemon start            Start the awareness daemon
    vigil daemon status           Check daemon status
    vigil signal <agent> <msg>    Emit a signal
    vigil status                  Show current awareness
    vigil frames                  List registered frames
    vigil tools [--frame X]       List tools (optionally filtered)
    vigil know <key> <value>      Store a knowledge entry
    vigil recall <query>          Fuzzy-search knowledge
    vigil knowledge               List all knowledge entries
    vigil forget <key>            Delete a knowledge entry
    vigil export                  Export state to markdown
    vigil doctor                  Diagnose common issues
    vigil version                 Show version
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path


def get_db_path() -> str:
    """Get the database path, respecting VIGIL_DB env var."""
    return os.environ.get("VIGIL_DB", "vigil.db")


def require_db() -> str:
    """Get DB path and exit if not initialized."""
    db_path = get_db_path()
    if not Path(db_path).exists():
        print(f"Not initialized. Run 'vigil init' first. (looked for {db_path})")
        sys.exit(1)
    return db_path


def cmd_init(args):
    """Initialize a new Vigil project."""
    from vigil.db import VigilDB

    db_path = get_db_path()
    if Path(db_path).exists() and not args.force:
        print(f"Database already exists at {db_path}. Use --force to reinitialize.")
        return

    db = VigilDB(db_path)

    # Register default frame
    db.register_frame("default", "Default frame — all tools visible", [])

    print(f"Vigil initialized at {db_path}")
    print()
    print("Next steps:")
    print("  vigil daemon start          # Start the awareness daemon")
    print("  vigil signal agent 'hello'  # Emit your first signal")
    print("  vigil status                # Check awareness state")


def cmd_daemon_start(args):
    """Start the awareness daemon."""
    from vigil.daemon import VigilDaemon

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [vigil] %(message)s",
        datefmt="%H:%M:%S",
    )

    db_path = require_db()

    daemon = VigilDaemon(
        db_path=db_path,
        compile_interval=args.interval,
        awareness_file=args.output,
    )

    print(f"Starting Vigil daemon (interval: {args.interval}s)")
    try:
        daemon.run()
    except KeyboardInterrupt:
        print("\nDaemon stopped.")


def cmd_daemon_status(args):
    """Check daemon status by reading brain_state."""
    from vigil.db import VigilDB

    db = VigilDB(require_db())
    state = db.get_brain_state()

    if not state or not state.get("compiled_at"):
        print("Daemon has not compiled yet.")
        return

    print(f"Frame:    {state.get('current_frame', 'unknown')}")
    print(f"Compiled: {state.get('compiled_at', 'never')}")

    ctx = state.get("hot_context", {})
    if isinstance(ctx, dict):
        print(f"Focus:    {len(ctx.get('focus', []))} items")
        print(f"Signals:  {ctx.get('recent_signals', 0)} in last hour")


def cmd_signal(args):
    """Emit a signal."""
    from vigil.db import VigilDB
    from vigil.signals import SignalBus

    db = VigilDB(require_db())
    bus = SignalBus(db)

    sig = bus.emit(
        from_agent=args.agent,
        content=args.message,
        signal_type=args.type,
    )

    print(f"Signal #{sig.id} emitted ({sig.signal_type.value}, {len(sig.content)} chars)")


def cmd_status(args):
    """Show current awareness."""
    from vigil.db import VigilDB

    db = VigilDB(require_db())

    awareness = db.get_awareness()
    if not awareness or not awareness.get("summary"):
        print("No awareness compiled yet.")
        return

    print(awareness["summary"])
    print(f"\n--- Updated: {awareness.get('updated_at', 'unknown')} by {awareness.get('updated_by', 'unknown')}")


def cmd_frames(args):
    """List registered frames."""
    from vigil.db import VigilDB

    db = VigilDB(require_db())
    frames = db.get_frames()

    if not frames:
        print("No frames registered.")
        return

    for f in frames:
        triggers = ", ".join(f.get("triggers", [])) or "(no triggers)"
        print(f"  {f['id']:15s}  {triggers}")


def cmd_tools(args):
    """List registered tools."""
    from vigil.registry import get_tools

    result = get_tools(frame=args.frame)
    tools = result["tools"]

    if not tools:
        print("No tools registered." + (f" (frame: {args.frame})" if args.frame else ""))
        return

    print(f"Tools ({len(tools)}):" + (f" [frame: {args.frame}]" if args.frame else ""))
    for t in tools:
        print(f"  {t['name']:25s}  {t['description'][:60]}")


def cmd_boot(args):
    """Show compiled hot context (what agents see on boot)."""
    from vigil.db import VigilDB
    from vigil.awareness import AwarenessCompiler

    db = VigilDB(require_db())
    compiler = AwarenessCompiler(db)
    context = compiler.boot()

    if args.json:
        print(json.dumps(context, indent=2))
    else:
        print(f"Frame:     {context.get('frame', 'unknown')}")
        print(f"Awareness: {context.get('awareness', 'none')[:200]}")
        focus = context.get("focus", [])
        if focus:
            print(f"Focus:     {len(focus)} items")
            for f in focus[:3]:
                print(f"  - [P{f.get('priority', '?')}] {f.get('task', '?')}")
        signals = context.get("recent_signals", 0)
        print(f"Signals:   {signals} in last hour")


def cmd_serve(args):
    """Start the Vigil MCP server."""
    from vigil.mcp_server import run_stdio, run_sse

    db_path = require_db()

    transport = args.transport
    print(f"Starting Vigil server (transport: {transport})")

    if transport == "http":
        from vigil.api import run_http
        print(f"  REST API: http://{args.host}:{args.port}")
        print(f"  Docs:     http://{args.host}:{args.port}/docs")
        run_http(db_path=db_path, host=args.host, port=args.port)
    elif transport == "sse":
        print(f"  MCP SSE: http://{args.host}:{args.port}")
        run_sse(db_path=db_path, host=args.host, port=args.port)
    else:
        run_stdio(db_path=db_path)


def cmd_handoff(args):
    """Write a structured session handoff."""
    from vigil.db import VigilDB
    from vigil.handoff import HandoffProtocol

    db = VigilDB(require_db())
    proto = HandoffProtocol(db)

    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    decisions = [d.strip() for d in args.decisions.split(",") if d.strip()] if args.decisions else []
    next_steps = [n.strip() for n in args.next_steps.split(",") if n.strip()] if args.next_steps else []

    handoff = proto.end_session(
        agent_id=args.agent,
        summary=args.summary,
        files_touched=files,
        decisions=decisions,
        next_steps=next_steps,
    )
    print(f"Handoff #{handoff.id} from {handoff.agent_id}")
    print(f"  Summary: {handoff.summary}")
    if next_steps:
        print(f"  Next: {', '.join(next_steps)}")


def cmd_resume(args):
    """Resume from last handoff."""
    from vigil.db import VigilDB
    from vigil.handoff import HandoffProtocol

    db = VigilDB(require_db())
    proto = HandoffProtocol(db)

    context = proto.resume(args.agent)

    last = context.get("last_handoff")
    if last:
        print(f"Last handoff from: {last['agent_id']}")
        print(f"  {last['summary']}")
        if last.get("next_steps"):
            steps = last["next_steps"]
            if isinstance(steps, list):
                for s in steps[:3]:
                    print(f"  Next: {s}")
    else:
        print("No previous handoffs found.")

    signals = context.get("signals_since_handoff", [])
    if signals:
        print(f"\n{len(signals)} signals since last handoff:")
        for s in signals[:5]:
            print(f"  [{s['from']}] {s['content'][:80]}")

    pending = context.get("pending_next_steps", [])
    if pending:
        print(f"\nPending next steps:")
        for p in pending[:5]:
            print(f"  [{p['from']}] {p['step']}")


def cmd_history(args):
    """Browse compacted signal history."""
    from vigil.db import VigilDB
    from vigil.compaction import SignalCompactor

    db = VigilDB(require_db())
    compactor = SignalCompactor(db)

    history = compactor.get_history(days=args.days, agent=args.agent)

    if not history:
        print(f"No compacted history in the last {args.days} days.")
        return

    print(f"Signal history ({len(history)} entries, last {args.days} days):\n")
    for entry in history:
        period = entry["period"].upper()
        agent = entry["agent_id"]
        count = entry["signal_count"]
        start = entry["date_range_start"][:10]
        end = entry["date_range_end"][:10]
        print(f"  [{period}] {agent} ({count} signals, {start} → {end})")
        print(f"    {entry['summary'][:120]}")
        print()


def cmd_agents(args):
    """List known agents."""
    from vigil.db import VigilDB

    db = VigilDB(require_db())

    # Try the agents table first (populated by MCP server)
    agents = db.query_all(
        "SELECT id, name, type, last_seen, session_count FROM agents ORDER BY last_seen DESC"
    )

    if agents:
        print(f"Registered agents ({len(agents)}):\n")
        for a in agents:
            print(f"  {a['id']:20s}  type={a['type']:8s}  sessions={a['session_count']}  last: {a['last_seen']}")
    else:
        # Fallback: derive from signals table
        from_signals = db.query_all(
            "SELECT from_agent, COUNT(*) as signal_count, "
            "MAX(created_at) as last_seen "
            "FROM signals GROUP BY from_agent ORDER BY last_seen DESC"
        )
        if not from_signals:
            print("No agents have emitted signals yet.")
            return
        print(f"Known agents ({len(from_signals)}):\n")
        for a in from_signals:
            print(f"  {a['from_agent']:20s}  {a['signal_count']:4d} signals  last: {a['last_seen']}")


def cmd_know(args):
    """Store a knowledge entry."""
    from vigil.db import VigilDB
    from vigil.knowledge import KnowledgeBase

    db = VigilDB(require_db())
    kb = KnowledgeBase(db)

    entry = kb.set(
        key=args.key,
        value=args.value,
        category=args.category,
        source_agent=args.agent,
        confidence=args.confidence,
    )
    print(f"Stored: {entry.key} = {entry.value}")
    if entry.category != "general":
        print(f"  Category: {entry.category}")


def cmd_recall(args):
    """Fuzzy-search knowledge."""
    from vigil.db import VigilDB
    from vigil.knowledge import KnowledgeBase

    db = VigilDB(require_db())
    kb = KnowledgeBase(db)

    results = kb.recall(args.query, category=args.category, limit=args.limit)

    if not results:
        print(f"No knowledge matches '{args.query}'.")
        return

    print(f"Knowledge ({len(results)} matches):\n")
    for e in results:
        agent_str = f" [{e.source_agent}]" if e.source_agent else ""
        cat_str = f" ({e.category})" if e.category != "general" else ""
        print(f"  {e.key}{cat_str}{agent_str}")
        print(f"    {e.value}")
        print()


def cmd_knowledge_list(args):
    """List all knowledge entries."""
    from vigil.db import VigilDB
    from vigil.knowledge import KnowledgeBase

    db = VigilDB(require_db())
    kb = KnowledgeBase(db)

    entries = kb.list(category=args.category, limit=args.limit)

    if not entries:
        print("No knowledge stored yet. Use 'vigil know <key> <value>' to add entries.")
        return

    # Group by category
    categories = {}
    for e in entries:
        cat = e.category or "general"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(e)

    total = kb.count()
    print(f"Knowledge ({total} entries):\n")
    for cat, items in sorted(categories.items()):
        print(f"  [{cat}]")
        for e in items:
            agent_str = f" ({e.source_agent})" if e.source_agent else ""
            print(f"    {e.key} = {e.value[:80]}{agent_str}")
        print()


def cmd_forget(args):
    """Delete a knowledge entry."""
    from vigil.db import VigilDB
    from vigil.knowledge import KnowledgeBase

    db = VigilDB(require_db())
    kb = KnowledgeBase(db)

    if kb.delete(args.key):
        print(f"Forgot: {args.key}")
    else:
        print(f"No knowledge entry found with key: {args.key}")


def cmd_version(args):
    """Show Vigil version."""
    from vigil import __version__
    print(f"vigil {__version__}")


def cmd_doctor(args):
    """Diagnose common issues."""
    from vigil import __version__
    from datetime import datetime, timezone

    checks = []

    # 1. DB exists
    db_path = get_db_path()
    db_exists = Path(db_path).exists()
    checks.append(("Database", "ok" if db_exists else "missing", db_path))

    if not db_exists:
        for label, status, detail in checks:
            mark = "+" if status == "ok" else "x"
            print(f"  [{mark}] {label}: {detail}")
        print(f"\nRun 'vigil init' to get started.")
        return

    from vigil.db import VigilDB
    db = VigilDB(db_path)

    # 2. Daemon compiled recently
    state = db.get_brain_state()
    if state and state.get("compiled_at"):
        compiled = state["compiled_at"]
        checks.append(("Daemon", "ok", f"last compiled {compiled}"))
    else:
        checks.append(("Daemon", "warn", "never compiled — run 'vigil daemon start'"))

    # 3. Signals flowing
    recent = db.get_recent_signals(hours=24, limit=1)
    signal_count = db.query_one("SELECT COUNT(*) as cnt FROM signals")
    total = signal_count["cnt"] if signal_count else 0
    if recent:
        checks.append(("Signals", "ok", f"{total} total, active in last 24h"))
    elif total > 0:
        checks.append(("Signals", "warn", f"{total} total, none in last 24h"))
    else:
        checks.append(("Signals", "warn", "no signals yet — try 'vigil signal agent \"hello\"'"))

    # 4. Frames registered
    frames = db.get_frames()
    checks.append(("Frames", "ok" if frames else "warn",
                    f"{len(frames)} registered" if frames else "none — register frames for filtering"))

    # 5. Focus items
    focus = db.get_active_focus()
    checks.append(("Focus", "ok" if focus else "info", f"{len(focus)} active items"))

    # 6. Optional deps
    deps = []
    try:
        import mcp
        deps.append("mcp")
    except ImportError:
        pass
    try:
        import fastapi
        deps.append("fastapi")
    except ImportError:
        pass
    try:
        import uvicorn
        deps.append("uvicorn")
    except ImportError:
        pass

    if deps:
        checks.append(("Dependencies", "ok", ", ".join(deps)))
    else:
        checks.append(("Dependencies", "info", "core only — install vigil-agent[server] for MCP/REST"))

    # Print results
    print(f"Vigil v{__version__} — Doctor\n")
    for label, status, detail in checks:
        if status == "ok":
            mark = "+"
        elif status == "warn":
            mark = "!"
        else:
            mark = "-"
        print(f"  [{mark}] {label}: {detail}")

    warnings = sum(1 for _, s, _ in checks if s == "warn")
    if warnings:
        print(f"\n{warnings} warning(s) found.")
    else:
        print(f"\nAll checks passed.")


def cmd_quickstart(args):
    """Interactive setup wizard for new Vigil projects."""
    from vigil.db import VigilDB
    from vigil.signals import SignalBus
    from vigil import __version__

    print(f"Vigil v{__version__} — Quickstart\n")

    # Step 1: Init
    db_path = get_db_path()
    if Path(db_path).exists():
        print(f"[1/4] Database already exists at {db_path}")
    else:
        db = VigilDB(db_path)
        db.register_frame("default", "Default frame — all tools visible", [])
        print(f"[1/4] Initialized database at {db_path}")

    db = VigilDB(db_path)

    # Step 2: Register example frames
    existing_frames = db.get_frames()
    existing_ids = {f["id"] for f in existing_frames}

    example_frames = [
        ("backend", "Backend development — APIs, databases, infrastructure", ["api", "db", "deploy"]),
        ("frontend", "Frontend development — UI, components, styling", ["ui", "component", "css"]),
        ("devops", "DevOps — CI/CD, monitoring, infrastructure", ["deploy", "ci", "monitor"]),
    ]

    added = 0
    for fid, desc, triggers in example_frames:
        if fid not in existing_ids:
            db.register_frame(fid, desc, triggers)
            added += 1

    if added:
        print(f"[2/4] Registered {added} example frames (backend, frontend, devops)")
    else:
        print(f"[2/4] Frames already configured ({len(existing_frames)} registered)")

    # Step 3: Emit a test signal
    bus = SignalBus(db)
    sig = bus.emit(
        from_agent="quickstart",
        content="Vigil quickstart completed — system initialized",
        signal_type="observation",
    )
    print(f"[3/4] Emitted test signal #{sig.id}")

    # Step 4: Next steps
    print(f"[4/4] Setup complete!\n")
    print("Next steps:")
    print(f"  vigil daemon start          # Start awareness daemon (runs in foreground)")
    print(f"  vigil signal myagent 'msg'  # Emit signals from your agents")
    print(f"  vigil status                # Check compiled awareness")
    print(f"  vigil serve --transport sse # Start MCP server (needs: pip install vigil-agent[mcp])")
    print(f"  vigil doctor                # Verify everything is working")
    print()
    print("Add to your AI tool config:")
    print('  {"mcpServers": {"vigil": {"command": "vigil", "args": ["serve"]}}}')


def cmd_export(args):
    """Export awareness state to markdown for pasting into LLM context."""
    from vigil.db import VigilDB
    from vigil.awareness import AwarenessCompiler
    from vigil import __version__
    import json as json_mod

    db = VigilDB(require_db())

    lines = []
    lines.append(f"# Vigil Context Export (v{__version__})")
    lines.append("")

    # Awareness
    awareness = db.get_awareness()
    if awareness and awareness.get("summary"):
        lines.append("## Awareness")
        lines.append(awareness["summary"])
        lines.append(f"_Updated: {awareness.get('updated_at', 'unknown')}_")
        lines.append("")

    # Frame
    state = db.get_brain_state()
    if state:
        lines.append(f"## Frame: {state.get('current_frame', 'unknown')}")
        lines.append(f"_Compiled: {state.get('compiled_at', 'never')}_")
        lines.append("")

    # Focus
    focus = db.get_active_focus(limit=10)
    if focus:
        lines.append("## Active Focus")
        for f in focus:
            lines.append(f"- [P{f['priority']}] {f['description']}" +
                        (f" ({f['owner']})" if f.get('owner') else ""))
        lines.append("")

    # Recent signals
    signals = db.get_recent_signals(hours=args.hours, limit=20)
    if signals:
        lines.append(f"## Recent Signals (last {args.hours}h)")
        for s in signals:
            lines.append(f"- [{s['from_agent']}/{s['signal_type']}] {s['content'][:120]}")
        lines.append("")

    # Last handoff
    handoff = db.query_one(
        "SELECT agent_id, summary, files_touched, decisions, next_steps, ended_at "
        "FROM handoffs ORDER BY ended_at DESC LIMIT 1"
    )
    if handoff:
        lines.append("## Last Handoff")
        lines.append(f"**Agent:** {handoff['agent_id']}  ")
        lines.append(f"**When:** {handoff['ended_at']}  ")
        lines.append(f"**Summary:** {handoff['summary']}")
        next_steps = handoff.get("next_steps", "[]")
        if isinstance(next_steps, str):
            try:
                next_steps = json_mod.loads(next_steps)
            except (json_mod.JSONDecodeError, TypeError):
                next_steps = []
        if next_steps:
            lines.append("**Next steps:**")
            for step in next_steps:
                lines.append(f"- {step}")
        lines.append("")

    # Frames
    frames = db.get_frames()
    if frames:
        lines.append("## Frames")
        for fr in frames:
            lines.append(f"- **{fr['id']}**: {fr.get('description', '')}")
        lines.append("")

    output = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Exported to {args.output} ({len(lines)} lines)")
    else:
        print(output)


def cmd_compact(args):
    """Run signal compaction manually."""
    from vigil.db import VigilDB
    from vigil.compaction import SignalCompactor

    db = VigilDB(require_db())
    compactor = SignalCompactor(db)

    stats = compactor.compact(dry_run=args.dry_run)

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}Compaction complete:")
    print(f"  Daily summaries:   {stats['daily_summaries']}")
    print(f"  Weekly digests:    {stats['weekly_digests']}")
    print(f"  Monthly snapshots: {stats['monthly_snapshots']}")
    print(f"  Signals compacted: {stats['signals_compacted']}")


def main():
    parser = argparse.ArgumentParser(
        prog="vigil",
        description="Cognitive infrastructure for AI agents",
    )
    subparsers = parser.add_subparsers(dest="command")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new Vigil project")
    init_parser.add_argument("--force", action="store_true", help="Reinitialize existing database")

    # daemon
    daemon_parser = subparsers.add_parser("daemon", help="Manage the awareness daemon")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_command")

    start_parser = daemon_sub.add_parser("start", help="Start the daemon")
    start_parser.add_argument("--interval", type=int, default=90, help="Compile interval in seconds (default: 90)")
    start_parser.add_argument("--output", type=str, default=None, help="Path to write AWARENESS.md")

    daemon_sub.add_parser("status", help="Check daemon status")

    # serve (MCP server)
    serve_parser = subparsers.add_parser("serve", help="Start the Vigil MCP server")
    serve_parser.add_argument("--transport", default="stdio", choices=["stdio", "sse", "http"], help="Transport protocol")
    serve_parser.add_argument("--host", default="127.0.0.1", help="SSE host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8300, help="SSE port (default: 8300)")

    # signal
    signal_parser = subparsers.add_parser("signal", help="Emit a signal")
    signal_parser.add_argument("agent", help="Agent identifier")
    signal_parser.add_argument("message", help="Signal content")
    signal_parser.add_argument("--type", default="observation", choices=["observation", "handoff", "summary", "alert"])

    # status
    subparsers.add_parser("status", help="Show current awareness")

    # frames
    subparsers.add_parser("frames", help="List registered frames")

    # tools
    tools_parser = subparsers.add_parser("tools", help="List registered tools")
    tools_parser.add_argument("--frame", default=None, help="Filter by frame")

    # boot
    boot_parser = subparsers.add_parser("boot", help="Show compiled hot context")
    boot_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # handoff
    handoff_parser = subparsers.add_parser("handoff", help="Write a structured session handoff")
    handoff_parser.add_argument("agent", help="Agent identifier")
    handoff_parser.add_argument("summary", help="What happened this session")
    handoff_parser.add_argument("--files", default="", help="Comma-separated files touched")
    handoff_parser.add_argument("--decisions", default="", help="Comma-separated decisions made")
    handoff_parser.add_argument("--next-steps", default="", dest="next_steps", help="Comma-separated next steps")

    # resume
    resume_parser = subparsers.add_parser("resume", help="Resume from last handoff")
    resume_parser.add_argument("agent", help="Agent identifier resuming work")

    # history
    history_parser = subparsers.add_parser("history", help="Browse compacted signal history")
    history_parser.add_argument("--days", type=int, default=30, help="Days to look back (default: 30)")
    history_parser.add_argument("--agent", default=None, help="Filter by agent")

    # agents
    subparsers.add_parser("agents", help="List known agents")

    # compact
    compact_parser = subparsers.add_parser("compact", help="Run signal compaction manually")
    compact_parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="Show what would be compacted without modifying data")

    # version
    subparsers.add_parser("version", help="Show Vigil version")

    # doctor
    subparsers.add_parser("doctor", help="Diagnose common issues")

    # know
    know_parser = subparsers.add_parser("know", help="Store a knowledge entry")
    know_parser.add_argument("key", help="Knowledge key")
    know_parser.add_argument("value", help="Knowledge value")
    know_parser.add_argument("--category", default="general", help="Category (default: general)")
    know_parser.add_argument("--agent", default=None, help="Source agent")
    know_parser.add_argument("--confidence", type=float, default=1.0, help="Confidence 0.0-1.0 (default: 1.0)")

    # recall
    recall_parser = subparsers.add_parser("recall", help="Fuzzy-search knowledge")
    recall_parser.add_argument("query", help="Search query")
    recall_parser.add_argument("--category", default=None, help="Filter by category")
    recall_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    # knowledge (list)
    knowledge_parser = subparsers.add_parser("knowledge", help="List all knowledge entries")
    knowledge_parser.add_argument("--category", default=None, help="Filter by category")
    knowledge_parser.add_argument("--limit", type=int, default=50, help="Max entries (default: 50)")

    # forget
    forget_parser = subparsers.add_parser("forget", help="Delete a knowledge entry")
    forget_parser.add_argument("key", help="Knowledge key to delete")

    # quickstart
    subparsers.add_parser("quickstart", help="Interactive setup wizard")

    # export
    export_parser = subparsers.add_parser("export", help="Export awareness state to markdown")
    export_parser.add_argument("--output", "-o", default=None, help="Write to file instead of stdout")
    export_parser.add_argument("--hours", type=int, default=24, help="Hours of signal history to include (default: 24)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "init": cmd_init,
        "daemon": lambda a: {
            "start": cmd_daemon_start,
            "status": cmd_daemon_status,
        }.get(a.daemon_command, lambda _: daemon_parser.print_help())(a),
        "serve": cmd_serve,
        "signal": cmd_signal,
        "status": cmd_status,
        "frames": cmd_frames,
        "tools": cmd_tools,
        "boot": cmd_boot,
        "handoff": cmd_handoff,
        "resume": cmd_resume,
        "history": cmd_history,
        "agents": cmd_agents,
        "compact": cmd_compact,
        "version": cmd_version,
        "doctor": cmd_doctor,
        "know": cmd_know,
        "recall": cmd_recall,
        "knowledge": cmd_knowledge_list,
        "forget": cmd_forget,
        "quickstart": cmd_quickstart,
        "export": cmd_export,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
