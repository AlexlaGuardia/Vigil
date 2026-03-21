"""
Vigil Daemon — Background awareness compilation on a fixed cycle.

The daemon runs in the background, compiling hot context at a
configurable interval (default 90s). Agents boot with pre-compiled
context instead of cold-starting every session.

Usage:
    daemon = VigilDaemon("vigil.db", compile_interval=90)
    daemon.run()  # Blocking
    # Or: daemon.start()  # Non-blocking (thread)
"""

import time
import logging
import threading
from typing import Optional, Callable

from vigil.db import VigilDB
from vigil.signals import SignalBus
from vigil.frames import FrameDetector
from vigil.awareness import AwarenessCompiler
from vigil.compaction import SignalCompactor
from vigil.triggers import TriggerEngine

log = logging.getLogger("vigil.daemon")


class VigilDaemon:
    """
    Background daemon that compiles awareness on a fixed cycle.

    Cycle architecture:
    - Every compile_interval: synthesize awareness + compile hot context
    - Every maintenance_interval: compress old signals, clean up
    - Optional: custom hooks run each cycle
    """

    def __init__(
        self,
        db_path: str = "vigil.db",
        compile_interval: int = 90,
        maintenance_interval: int = 3600,
        default_frame: str = "default",
        awareness_file: Optional[str] = None,
        on_compile: Optional[Callable[[dict], None]] = None,
    ):
        """
        Args:
            db_path: Path to SQLite database
            compile_interval: Seconds between compile cycles (default 90)
            maintenance_interval: Seconds between maintenance runs (default 3600)
            default_frame: Default frame when no triggers match
            awareness_file: Optional path to write awareness markdown
            on_compile: Optional callback after each compilation
        """
        self.db = VigilDB(db_path)
        self.signals = SignalBus(self.db)
        self.frames = FrameDetector(self.db, default_frame=default_frame)
        self.compiler = AwarenessCompiler(self.db, frame_detector=self.frames)
        self.compactor = SignalCompactor(self.db)
        self.triggers = TriggerEngine(self.db, self.signals)

        self.compile_interval = compile_interval
        self.maintenance_interval = maintenance_interval
        self.awareness_file = awareness_file
        self.on_compile = on_compile

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def run(self):
        """Run the daemon (blocking)."""
        self._running = True
        last_maintenance = 0

        log.info(
            f"Vigil daemon starting (compile: {self.compile_interval}s, "
            f"maintenance: {self.maintenance_interval}s)"
        )

        while self._running:
            try:
                # Synthesize + compile
                self.compiler.synthesize()
                context = self.compiler.compile()

                log.info(
                    f"Compiled: frame={context['frame']}, "
                    f"focus={len(context.get('focus', []))}, "
                    f"signals={context.get('recent_signals', 0)}"
                )

                # Evaluate triggers against recent signals
                try:
                    fired = self.triggers.evaluate_recent(hours=1)
                    if fired:
                        log.info(f"Triggers: {len(fired)} fired")
                except Exception as e:
                    log.error(f"Trigger evaluation error: {e}")

                # Write awareness file if configured
                if self.awareness_file:
                    self._write_awareness(context)

                # Custom hook
                if self.on_compile:
                    try:
                        self.on_compile(context)
                    except Exception as e:
                        log.error(f"on_compile hook error: {e}")

                # Maintenance cycle
                if time.time() - last_maintenance > self.maintenance_interval:
                    deleted = self.db.compress_old_signals(days_old=7)
                    if deleted > 0:
                        log.info(f"Maintenance: compressed {deleted} old signals")
                    # Run tiered compaction
                    try:
                        stats = self.compactor.compact()
                        if stats["daily_summaries"] or stats["weekly_digests"] or stats["monthly_snapshots"]:
                            log.info(
                                f"Compaction: {stats['daily_summaries']} daily, "
                                f"{stats['weekly_digests']} weekly, "
                                f"{stats['monthly_snapshots']} monthly"
                            )
                    except Exception as e:
                        log.error(f"Compaction error: {e}")
                    last_maintenance = time.time()

            except Exception as e:
                log.error(f"Daemon cycle error: {e}")

            time.sleep(self.compile_interval)

    def start(self):
        """Start the daemon in a background thread."""
        if self._thread and self._thread.is_alive():
            log.warning("Daemon already running")
            return
        self._thread = threading.Thread(target=self.run, daemon=True, name="vigil-daemon")
        self._thread.start()
        log.info("Daemon started in background thread")

    def stop(self):
        """Stop the daemon."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.compile_interval + 5)
        log.info("Daemon stopped")

    def _write_awareness(self, context: dict):
        """Write awareness to a markdown file."""
        try:
            focus_items = context.get("focus", [])
            focus_str = "\n".join(
                f"- [P{f['priority']}] {f['task']}"
                + (f" ({f['owner']})" if f.get("owner") else "")
                for f in focus_items
            ) if focus_items else "No active focus items"

            signals = context.get("_signals", [])
            signals_str = "\n".join(
                f"- [{s['from']}/{s['type']}] {s['content']}"
                for s in signals
            ) if signals else "No recent signals"

            content = f"""# Awareness
> Auto-compiled by Vigil daemon every {self.compile_interval}s.
> Last compiled: {context.get('compiled_at', 'unknown')}

## Current State
- **Frame**: {context.get('frame', 'default')}

## Session Context
{context.get('awareness', 'No awareness')}

## Active Focus
{focus_str}

## Recent Signals ({context.get('recent_signals', 0)} in last hour)
{signals_str}
"""
            with open(self.awareness_file, "w") as f:
                f.write(content)
        except Exception as e:
            log.error(f"Awareness file write error: {e}")
