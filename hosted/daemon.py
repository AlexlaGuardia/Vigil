"""Multi-tenant awareness daemon — cycles through active tenants.

Runs as a background thread inside the hosted FastAPI process.
Each cycle: iterates active projects, compiles awareness for each.
Lightweight — only touches tenants with recent signals.
"""

import time
import logging
import threading
from datetime import datetime, timedelta

from hosted.tenant import get_tenant_state, get_tenant_db_path
from hosted.config import DATA_DIR

log = logging.getLogger("vigil.hosted.daemon")


class HostedDaemon:
    """Multi-tenant awareness daemon.

    Cycles through active tenants every `interval` seconds.
    Only compiles awareness for tenants with signals in the last `active_window` hours.
    """

    def __init__(self, platform_db, interval: int = 120, active_window: int = 24):
        """
        Args:
            platform_db: PlatformDB instance for querying active projects
            interval: Seconds between full cycles (default 120)
            active_window: Only compile tenants with activity in last N hours (default 24)
        """
        self.pdb = platform_db
        self.interval = interval
        self.active_window = active_window
        self._running = False
        self._thread = None
        self._stats = {"cycles": 0, "tenants_compiled": 0, "last_cycle": None}

    def start(self):
        """Start the daemon in a background thread."""
        if self._thread and self._thread.is_alive():
            log.warning("Hosted daemon already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="vigil-hosted-daemon")
        self._thread.start()
        log.info(f"Hosted daemon started (interval={self.interval}s, active_window={self.active_window}h)")

    def stop(self):
        """Stop the daemon."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        log.info("Hosted daemon stopped")

    def _run(self):
        """Main daemon loop."""
        while self._running:
            try:
                self._cycle()
            except Exception as e:
                log.error(f"Daemon cycle error: {e}")
            time.sleep(self.interval)

    def _cycle(self):
        """Run one compile cycle across all active tenants."""
        active_projects = self._get_active_projects()

        compiled = 0
        for project_id in active_projects:
            try:
                state = get_tenant_state(project_id)
                state["compiler"].synthesize()
                state["compiler"].compile()
                compiled += 1
            except Exception as e:
                log.error(f"Compile error for {project_id[:8]}: {e}")

        self._stats["cycles"] += 1
        self._stats["tenants_compiled"] += compiled
        self._stats["last_cycle"] = datetime.utcnow().isoformat()

        if compiled > 0:
            log.info(f"Cycle #{self._stats['cycles']}: compiled {compiled}/{len(active_projects)} tenants")

    def _get_active_projects(self) -> list[str]:
        """Get project IDs with recent usage (signals in the active window)."""
        cutoff = (datetime.utcnow() - timedelta(hours=self.active_window)).strftime("%Y-%m")
        with self.pdb.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project_id FROM usage WHERE month >= ? AND signal_count > 0",
                (cutoff,),
            ).fetchall()
            return [r["project_id"] for r in rows]

    @property
    def stats(self) -> dict:
        return self._stats.copy()
