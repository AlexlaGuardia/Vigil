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
        "signal": cmd_signal,
        "status": cmd_status,
        "frames": cmd_frames,
        "tools": cmd_tools,
        "boot": cmd_boot,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
