"""
Vigil CLI — Command-line interface for managing the daemon and signals.

Usage:
    vigil init                    Initialize a new Vigil project
    vigil daemon start            Start the awareness daemon
    vigil daemon status           Check daemon status
    vigil signal <agent> <msg>    Emit a signal
    vigil status                  Show current awareness
    vigil frames                  List registered frames
    vigil tools [--frame X]       List tools (optionally filtered)
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

    db_path = get_db_path()
    if not Path(db_path).exists():
        print(f"No database at {db_path}. Run 'vigil init' first.")
        sys.exit(1)

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

    db_path = get_db_path()
    if not Path(db_path).exists():
        print("Not initialized. Run 'vigil init' first.")
        sys.exit(1)

    db = VigilDB(db_path)
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

    db = VigilDB(get_db_path())
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

    db = VigilDB(get_db_path())

    awareness = db.get_awareness()
    if not awareness or not awareness.get("summary"):
        print("No awareness compiled yet.")
        return

    print(awareness["summary"])
    print(f"\n--- Updated: {awareness.get('updated_at', 'unknown')} by {awareness.get('updated_by', 'unknown')}")


def cmd_frames(args):
    """List registered frames."""
    from vigil.db import VigilDB

    db = VigilDB(get_db_path())
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

    db = VigilDB(get_db_path())
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

    db_path = get_db_path()
    if not Path(db_path).exists():
        print(f"No database at {db_path}. Run 'vigil init' first.")
        sys.exit(1)

    transport = args.transport
    print(f"Starting Vigil MCP server (transport: {transport})")

    if transport == "sse":
        print(f"  Host: {args.host}:{args.port}")
        run_sse(db_path=db_path, host=args.host, port=args.port)
    else:
        run_stdio(db_path=db_path)


def cmd_handoff(args):
    """Write a structured session handoff."""
    from vigil.db import VigilDB
    from vigil.handoff import HandoffProtocol

    db = VigilDB(get_db_path())
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

    db = VigilDB(get_db_path())
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

    db = VigilDB(get_db_path())
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

    db = VigilDB(get_db_path())

    agents = db.query_all(
        "SELECT from_agent, COUNT(*) as signal_count, "
        "MAX(created_at) as last_seen "
        "FROM signals GROUP BY from_agent ORDER BY last_seen DESC"
    )

    if not agents:
        print("No agents have emitted signals yet.")
        return

    print(f"Known agents ({len(agents)}):\n")
    for a in agents:
        print(f"  {a['from_agent']:20s}  {a['signal_count']:4d} signals  last: {a['last_seen']}")


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
    serve_parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"], help="Transport protocol")
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
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
