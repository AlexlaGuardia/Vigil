"""
MCPWatch — Production observability for MCP servers.

One-line instrumentation that turns Vigil into a monitoring layer.
Tracks tool calls, latency, errors, and emits alerts.

Usage:
    from mcp.server.fastmcp import FastMCP
    from vigil.mcpwatch import instrument

    mcp = FastMCP("my-server")

    @mcp.tool()
    async def my_tool(query: str) -> str:
        ...

    # One line — instruments all registered tools
    watch = instrument(mcp)

    # Or with Vigil Cloud
    watch = instrument(mcp, api_key="vgl_...", server_name="my-server")

    # Check health anytime
    health = watch.health()
"""

import asyncio
import functools
import hashlib
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable, Any


@dataclass
class ToolEvent:
    """A single tool call event."""
    server_name: str
    tool_name: str
    duration_ms: float
    status: str = "success"  # success | error | silent
    error: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error": self.error,
            "created_at": (self.created_at or datetime.now(timezone.utc)).isoformat(),
        }


@dataclass
class ToolStats:
    """Aggregated stats for a single tool."""
    name: str
    call_count: int = 0
    error_count: int = 0
    silent_count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    durations: list = field(default_factory=list)  # for percentiles

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.call_count if self.call_count else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.durations:
            return 0.0
        sorted_d = sorted(self.durations)
        idx = int(len(sorted_d) * 0.95)
        return sorted_d[min(idx, len(sorted_d) - 1)]

    @property
    def p99_ms(self) -> float:
        if not self.durations:
            return 0.0
        sorted_d = sorted(self.durations)
        idx = int(len(sorted_d) * 0.99)
        return sorted_d[min(idx, len(sorted_d) - 1)]

    @property
    def error_rate(self) -> float:
        return self.error_count / self.call_count if self.call_count else 0.0

    @property
    def silent_rate(self) -> float:
        return self.silent_count / self.call_count if self.call_count else 0.0

    def record(self, duration_ms: float, is_error: bool = False, is_silent: bool = False):
        self.call_count += 1
        self.total_ms += duration_ms
        self.min_ms = min(self.min_ms, duration_ms)
        self.max_ms = max(self.max_ms, duration_ms)
        # Keep last 1000 durations for percentile calculation
        self.durations.append(duration_ms)
        if len(self.durations) > 1000:
            self.durations = self.durations[-1000:]
        if is_error:
            self.error_count += 1
        if is_silent:
            self.silent_count += 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "call_count": self.call_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "silent_count": self.silent_count,
            "silent_rate": round(self.silent_rate, 4),
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2) if self.min_ms != float("inf") else 0.0,
            "max_ms": round(self.max_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
        }


class MCPWatch:
    """MCP server monitoring engine.

    Wraps tool handlers to track calls, latency, and errors.
    Stores events in Vigil DB and optionally sends to Vigil Cloud.

    Args:
        server_name: Name of the MCP server being monitored
        db: Optional VigilDB instance for local storage
        api_key: Optional Vigil Cloud API key (reads VIGIL_API_KEY env)
        api_url: Vigil Cloud API URL
        latency_threshold_ms: Alert when tool call exceeds this (default: 5000ms)
        silence_threshold_min: Alert when no calls for this long (default: 60 min)
    """

    def __init__(
        self,
        server_name: str = "mcp-server",
        db=None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        latency_threshold_ms: float = 5000.0,
        silence_threshold_min: int = 60,
        attributor: Optional[Callable] = None,
    ):
        self.server_name = server_name
        self.db = db
        self.api_key = api_key or os.environ.get("VIGIL_API_KEY", "")
        self.api_url = (api_url or os.environ.get("VIGIL_API_URL", "https://app.vigil-agent.com")).rstrip("/")
        self.latency_threshold_ms = latency_threshold_ms
        self.silence_threshold_min = silence_threshold_min

        # In-memory stats (fast, no DB hit per call)
        self._stats: dict[str, ToolStats] = {}
        self._recent_errors: list[ToolEvent] = []
        self._recent_silent: list[ToolEvent] = []
        self._started_at = datetime.now(timezone.utc)
        self._last_call_at: Optional[datetime] = None
        self._total_calls = 0
        self._total_errors = 0
        self._total_silent = 0
        self._scan_results: list = []  # scan-tools registration-time results
        # Attribution hook (the Crumb tie-in). When a tool that scan-tools flagged HIGH
        # at registration actually executes, we hand the call event to this callback so
        # an attribution layer can bind it to the human who authorized the session. Vigil
        # deliberately does NOT resolve the human itself — that's the attributor's job
        # (Crumb pulls it from the session/RFC8693 token); Vigil supplies only the trigger
        # and the call context. Keeps Vigil standalone; makes the Crumb tie-in a real hook.
        self._attributor = attributor
        self._flagged_tools: dict = {}  # tool_name -> [flagged field paths] (HIGH at registration)

        # Initialize DB table if local
        if self.db:
            self._init_db()

    def _init_db(self):
        """Create mcp_events table if it doesn't exist."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS mcp_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'success',
                error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_events_server ON mcp_events(server_name)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_events_created ON mcp_events(created_at)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_events_tool ON mcp_events(tool_name)"
        )

    # ── Silent-failure detection ─────────────────────────────────
    #
    # A "silent failure" is a tool call that looks successful — no exception
    # raised, no isError flag — but returns nothing usable: None, an empty or
    # whitespace-only string, an empty list, or a content payload with no real
    # text/data. These are the failures an agent doesn't tell you about: the
    # model gets back an empty result and quietly hallucinates around it. This
    # is the one signal generic MCP monitors and gateways don't surface.
    #
    # Detection is deliberately conservative: legitimate falsy values like 0,
    # False, or a populated dict are NOT silent. Classification never raises —
    # monitoring must never break the server it watches.

    def _is_silent_result(self, result: Any) -> bool:
        """Decide whether a tool's return value is a silent failure."""
        try:
            if result is None:
                return True
            if isinstance(result, str):
                return result.strip() == ""
            if isinstance(result, (bytes, bytearray)):
                return len(result) == 0
            # Content-bearing result objects (CallToolResult / ServerResult.root)
            inner = getattr(result, "root", result)
            if getattr(inner, "isError", False):
                return False  # explicit error — handled by the error path
            if hasattr(inner, "content"):
                return self._content_is_empty(getattr(inner, "content"))
            # dict-shaped results (some tools return raw dicts)
            if isinstance(result, dict):
                if result.get("isError"):
                    return False
                if "content" in result:
                    return self._content_is_empty(result["content"])
                return False  # populated dict carries data — not silent
            if isinstance(result, (list, tuple)):
                return self._content_is_empty(result)
            return False
        except Exception:
            return False

    @staticmethod
    def _content_is_empty(content: Any) -> bool:
        """True if a content payload carries nothing usable: None, empty, or
        only empty/whitespace text items. Any non-text item (image, resource,
        etc.) counts as real payload."""
        if content is None:
            return True
        if isinstance(content, str):
            return content.strip() == ""
        if isinstance(content, (bytes, bytearray)):
            return len(content) == 0
        try:
            items = list(content)
        except TypeError:
            return False
        if not items:
            return True
        for item in items:
            if isinstance(item, dict):
                if item.get("type", "text") != "text":
                    return False  # non-text content = real payload
                text = item.get("text")
            elif hasattr(item, "text") and getattr(item, "type", "text") == "text":
                text = getattr(item, "text")
            else:
                return False  # unknown / non-text content item = real payload
            if text is not None and str(text).strip() != "":
                return False  # found real text → not empty
        return True  # every item was empty text

    def _wrap(self, tool_name: str, original_fn: Callable) -> Callable:
        """Wrap a tool function with monitoring."""

        if asyncio.iscoroutinefunction(original_fn):
            @functools.wraps(original_fn)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                error_msg = None
                status = "success"
                try:
                    result = await original_fn(*args, **kwargs)
                    if self._is_silent_result(result):
                        status = "silent"
                    return result
                except Exception as e:
                    status = "error"
                    error_msg = f"{type(e).__name__}: {str(e)[:500]}"
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    self._record(tool_name, duration_ms, status, error_msg)
            return async_wrapper
        else:
            @functools.wraps(original_fn)
            def sync_wrapper(*args, **kwargs):
                start = time.perf_counter()
                error_msg = None
                status = "success"
                try:
                    result = original_fn(*args, **kwargs)
                    if self._is_silent_result(result):
                        status = "silent"
                    return result
                except Exception as e:
                    status = "error"
                    error_msg = f"{type(e).__name__}: {str(e)[:500]}"
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    self._record(tool_name, duration_ms, status, error_msg)
            return sync_wrapper

    def _record(self, tool_name: str, duration_ms: float, status: str, error: Optional[str]):
        """Record a tool call event."""
        now = datetime.now(timezone.utc)
        is_error = status == "error"
        is_silent = status == "silent"

        # Update in-memory stats
        if tool_name not in self._stats:
            self._stats[tool_name] = ToolStats(name=tool_name)
        self._stats[tool_name].record(duration_ms, is_error, is_silent)

        self._total_calls += 1
        self._last_call_at = now
        if is_error:
            self._total_errors += 1
        if is_silent:
            self._total_silent += 1

        event = ToolEvent(
            server_name=self.server_name,
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            error=error,
            created_at=now,
        )

        # Store error in recent buffer (keep last 100)
        if is_error:
            self._recent_errors.append(event)
            if len(self._recent_errors) > 100:
                self._recent_errors = self._recent_errors[-100:]

        # Store silent failures in their own recent buffer (keep last 100)
        if is_silent:
            self._recent_silent.append(event)
            if len(self._recent_silent) > 100:
                self._recent_silent = self._recent_silent[-100:]

        # Persist to DB
        if self.db:
            try:
                self.db.execute(
                    "INSERT INTO mcp_events (server_name, tool_name, duration_ms, status, error) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.server_name, tool_name, duration_ms, status, error),
                )
            except Exception:
                pass  # Don't let monitoring failures break the server

        # Emit Vigil signals for alerts
        if is_error:
            self._emit_signal(
                f"[mcpwatch/{self.server_name}] Tool error: {tool_name} — {error}",
                signal_type="alert",
            )
        elif is_silent:
            self._emit_signal(
                f"[mcpwatch/{self.server_name}] Silent failure: {tool_name} returned an empty/null result with no error raised",
                signal_type="alert",
            )
        elif duration_ms > self.latency_threshold_ms:
            self._emit_signal(
                f"[mcpwatch/{self.server_name}] Slow tool: {tool_name} took {duration_ms:.0f}ms (threshold: {self.latency_threshold_ms:.0f}ms)",
                signal_type="alert",
            )

        # Attribution tie-in (Crumb): a tool scan-tools flagged HIGH at registration just
        # executed — the call that walked through the door §5 says a static scan can't stop.
        # Hand it to the attributor so the actual call gets bound to the authorizing human.
        # Guarded: an attributor that raises must never break the monitored call.
        if self._attributor and tool_name in self._flagged_tools:
            try:
                self._attributor({
                    "server": self.server_name,
                    "tool_name": tool_name,
                    "status": status,
                    "reason": "call to a tool flagged HIGH at registration (scan-tools)",
                    "flagged_fields": self._flagged_tools[tool_name],
                    "timestamp": now.isoformat(),
                })
            except Exception:
                pass

    def _emit_signal(self, content: str, signal_type: str = "observation"):
        """Emit a Vigil signal — local DB or cloud API."""
        if self.db:
            try:
                from vigil.signals import SignalBus
                bus = SignalBus(self.db)
                bus.emit(
                    from_agent=f"mcpwatch/{self.server_name}",
                    content=content,
                    signal_type=signal_type,
                )
            except Exception:
                pass
        elif self.api_key:
            try:
                import json
                from urllib.request import Request, urlopen
                url = f"{self.api_url}/api/signal"
                data = json.dumps({
                    "agent": f"mcpwatch/{self.server_name}",
                    "content": content,
                    "signal_type": signal_type,
                }).encode()
                req = Request(url, data=data, method="POST")
                req.add_header("Authorization", f"Bearer {self.api_key}")
                req.add_header("Content-Type", "application/json")
                urlopen(req, timeout=5)
            except Exception:
                pass

    def scan_registration(self, server) -> list:
        """Registration-time tool-definition scan (scan-tools) — the pre-flight half
        of the pair. MCPWatch watches calls at runtime; this inspects the definitions
        before the first call ever happens. A HIGH flag emits an alert immediately,
        because a poisoned tool is a problem the moment it's registered, not just when
        it fires. Best-effort: a server whose tools can't be read yields an empty scan
        rather than raising."""
        try:
            from vigil.scantools import scan_server
            results = scan_server(server)
        except Exception:
            return []
        self._scan_results = results
        self._flagged_tools = {
            r.tool_name: sorted({f.field_path for f in r.flags})
            for r in results if r.severity == "high"
        }
        for r in results:
            if r.severity == "high":
                paths = ", ".join(sorted({f.field_path for f in r.flags}))
                self._emit_signal(
                    f"scan-tools: HIGH — tool '{r.tool_name}' carries an imperative "
                    f"directive at {paths} (flagged at registration, before first call)",
                    signal_type="alert",
                )
        return results

    # ── Public API ───────────────────────────────────────────────

    def health(self) -> dict:
        """Get server health summary.

        Returns:
            {
                "server": str,
                "status": "healthy" | "degraded" | "unhealthy",
                "uptime_seconds": float,
                "total_calls": int,
                "total_errors": int,
                "error_rate": float,
                "last_call_at": str | None,
                "tools_monitored": int,
                "tools": {name: stats_dict}
            }
        """
        now = datetime.now(timezone.utc)
        uptime = (now - self._started_at).total_seconds()

        # Determine status
        error_rate = self._total_errors / self._total_calls if self._total_calls else 0.0
        silent_rate = self._total_silent / self._total_calls if self._total_calls else 0.0
        is_silent = (
            self._last_call_at
            and (now - self._last_call_at) > timedelta(minutes=self.silence_threshold_min)
        )

        if error_rate > 0.5 or silent_rate > 0.5 or is_silent:
            status = "unhealthy"
        elif error_rate > 0.1 or silent_rate > 0.1:
            status = "degraded"
        else:
            status = "healthy"

        # Registration-time scan (scan-tools), surfaced alongside runtime health so a
        # poisoned tool is visible before it's ever called — two checkpoints, one pane.
        # A HIGH poisoning flag is its own signal, not a runtime error, so it bumps a
        # healthy server to "degraded" (visible) without overriding a real runtime fault.
        flagged = [r for r in self._scan_results if r.flagged]
        if any(r.severity == "high" for r in flagged) and status == "healthy":
            status = "degraded"

        return {
            "server": self.server_name,
            "status": status,
            "uptime_seconds": round(uptime, 1),
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "error_rate": round(error_rate, 4),
            "total_silent": self._total_silent,
            "silent_rate": round(silent_rate, 4),
            "last_call_at": self._last_call_at.isoformat() if self._last_call_at else None,
            "tools_monitored": len(self._stats),
            "tools": {name: s.to_dict() for name, s in self._stats.items()},
            "registration_scan": {
                "tools_scanned": len(self._scan_results),
                "flagged": [
                    {"tool_name": r.tool_name, "severity": r.severity,
                     "fields": sorted({f.field_path for f in r.flags})}
                    for r in flagged
                ],
            },
        }

    def tool_stats(self, tool_name: str) -> Optional[dict]:
        """Get stats for a specific tool."""
        stats = self._stats.get(tool_name)
        return stats.to_dict() if stats else None

    def recent_errors(self, limit: int = 20) -> list[dict]:
        """Get recent errors."""
        return [e.to_dict() for e in self._recent_errors[-limit:]]

    def recent_silent(self, limit: int = 20) -> list[dict]:
        """Get recent silent failures (empty/null returns with no error)."""
        return [e.to_dict() for e in self._recent_silent[-limit:]]

    def is_silent(self) -> bool:
        """Check if the server has gone silent (no calls for threshold period)."""
        if not self._last_call_at:
            return False
        return (datetime.now(timezone.utc) - self._last_call_at) > timedelta(minutes=self.silence_threshold_min)

    def reset(self):
        """Reset all in-memory stats."""
        self._stats.clear()
        self._recent_errors.clear()
        self._recent_silent.clear()
        self._total_calls = 0
        self._total_errors = 0
        self._total_silent = 0
        self._started_at = datetime.now(timezone.utc)
        self._last_call_at = None

    # ── DB queries (for dashboard) ───────────────────────────────

    def db_tool_stats(self, hours: int = 24) -> list[dict]:
        """Get per-tool stats from DB over a time window."""
        if not self.db:
            return []
        return self.db.query_all(
            "SELECT tool_name, COUNT(*) as call_count, "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as error_count, "
            "SUM(CASE WHEN status='silent' THEN 1 ELSE 0 END) as silent_count, "
            "AVG(duration_ms) as avg_ms, "
            "MIN(duration_ms) as min_ms, "
            "MAX(duration_ms) as max_ms "
            "FROM mcp_events WHERE server_name = ? "
            "AND created_at > datetime('now', ?) "
            "GROUP BY tool_name ORDER BY call_count DESC",
            (self.server_name, f"-{hours} hours"),
        )

    def db_recent_errors(self, limit: int = 20) -> list[dict]:
        """Get recent errors from DB."""
        if not self.db:
            return []
        return self.db.query_all(
            "SELECT tool_name, duration_ms, error, created_at "
            "FROM mcp_events WHERE server_name = ? AND status = 'error' "
            "ORDER BY created_at DESC LIMIT ?",
            (self.server_name, limit),
        )

    def db_silent_failures(self, limit: int = 20) -> list[dict]:
        """Get recent silent failures from DB (empty/null returns, no error)."""
        if not self.db:
            return []
        return self.db.query_all(
            "SELECT tool_name, duration_ms, created_at "
            "FROM mcp_events WHERE server_name = ? AND status = 'silent' "
            "ORDER BY created_at DESC LIMIT ?",
            (self.server_name, limit),
        )

    def db_call_volume(self, hours: int = 24, bucket_minutes: int = 60) -> list[dict]:
        """Get call volume over time (for charts)."""
        if not self.db:
            return []
        return self.db.query_all(
            "SELECT strftime('%Y-%m-%d %H:00', created_at) as bucket, "
            "COUNT(*) as calls, "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors, "
            "SUM(CASE WHEN status='silent' THEN 1 ELSE 0 END) as silent, "
            "AVG(duration_ms) as avg_ms "
            "FROM mcp_events WHERE server_name = ? "
            "AND created_at > datetime('now', ?) "
            "GROUP BY bucket ORDER BY bucket",
            (self.server_name, f"-{hours} hours"),
        )

    def db_latency_percentiles(self, hours: int = 24) -> dict:
        """Get latency percentiles from DB."""
        if not self.db:
            return {}
        rows = self.db.query_all(
            "SELECT duration_ms FROM mcp_events WHERE server_name = ? "
            "AND created_at > datetime('now', ?) ORDER BY duration_ms",
            (self.server_name, f"-{hours} hours"),
        )
        if not rows:
            return {"p50": 0, "p95": 0, "p99": 0, "count": 0}
        durations = [r["duration_ms"] for r in rows]
        n = len(durations)
        return {
            "p50": round(durations[int(n * 0.50)], 2),
            "p95": round(durations[int(n * 0.95)], 2),
            "p99": round(durations[min(int(n * 0.99), n - 1)], 2),
            "count": n,
        }


# ── Public API ───────────────────────────────────────────────────

def instrument(
    server,
    server_name: Optional[str] = None,
    db=None,
    db_path: Optional[str] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    latency_threshold_ms: float = 5000.0,
    silence_threshold_min: int = 60,
    scan_on_register: bool = True,
    attributor: Optional[Callable] = None,
) -> MCPWatch:
    """Instrument an MCP server with production monitoring.

    One-line setup that wraps all registered tools with latency tracking,
    error detection, and alert emission. Works with both the high-level
    FastMCP class and the low-level mcp.server.lowlevel.Server class.

    Args:
        server: FastMCP or low-level Server instance
        server_name: Name for this server (default: server.name)
        db: VigilDB instance (for local Vigil)
        db_path: Path to Vigil DB (creates VigilDB if no db provided)
        api_key: Vigil Cloud API key (reads VIGIL_API_KEY env)
        api_url: Vigil Cloud API URL
        latency_threshold_ms: Alert threshold in ms (default: 5000)
        silence_threshold_min: Silent server alert threshold (default: 60)
        scan_on_register: Run the scan-tools tool-definition scan at registration
            (default: True — opt-out). Flags an imperative directive hidden in any
            schema field before the tool's first call; a HIGH flag emits an alert.
        attributor: Optional callback(event: dict) invoked when a tool that scanned
            HIGH at registration actually executes — the Crumb tie-in. Vigil supplies
            the call context (tool, status, flagged fields, timestamp); the attributor
            binds it to the authorizing human. Vigil never resolves the human itself,
            so it carries no attribution dependency. See docs/scan-tools-design.md §5.

    Returns:
        MCPWatch instance with health(), tool_stats(), recent_errors()

    Example (FastMCP):
        from mcp.server.fastmcp import FastMCP
        from vigil.mcpwatch import instrument

        mcp = FastMCP("my-server")

        @mcp.tool()
        async def search(query: str) -> str:
            return "results"

        watch = instrument(mcp)

    Example (low-level Server):
        from mcp.server.lowlevel import Server
        from vigil.mcpwatch import instrument

        server = Server("my-server")

        @server.call_tool()
        async def call_tool(name, arguments):
            return [...]

        watch = instrument(server)
    """
    name = server_name or getattr(server, "name", "mcp-server")

    # Set up DB if path provided
    if db is None and db_path:
        from vigil.db import VigilDB
        db = VigilDB(db_path)

    watch = MCPWatch(
        server_name=name,
        db=db,
        api_key=api_key,
        api_url=api_url,
        latency_threshold_ms=latency_threshold_ms,
        silence_threshold_min=silence_threshold_min,
        attributor=attributor,
    )

    # Wrap all registered tools — dispatches by server type
    _patch_server(server, watch)

    # Pre-flight: scan tool definitions at registration (the scan-tools half of the
    # pair). Runtime monitoring catches misbehavior when it fires; this catches a
    # poisoned definition before the first call.
    if scan_on_register:
        watch.scan_registration(server)

    return watch


def _patch_server(server, watch: MCPWatch):
    """Patch a server's tool handlers with monitoring wrappers.

    Dispatches by server type:
    - FastMCP: patches server._tool_manager.tools[].fn (per-tool wrap)
    - Low-level Server: patches request_handlers[CallToolRequest] (single dispatcher wrap)

    Both paths are no-ops if the expected structure is absent.
    """
    if hasattr(server, "_tool_manager"):
        _patch_fastmcp_server(server, watch)
        return
    if hasattr(server, "request_handlers"):
        _patch_low_level_server(server, watch)
        return


def _patch_fastmcp_server(server, watch: MCPWatch):
    """Patch a FastMCP server's registered tools with monitoring wrappers.

    Handles the FastMCP internal structure: server._tool_manager.tools
    is a dict of {name: Tool} where each Tool has a .fn attribute.
    """
    tool_manager = getattr(server, "_tool_manager", None)
    if tool_manager is None:
        return

    tools = getattr(tool_manager, "tools", None) or getattr(tool_manager, "_tools", {})

    for name, tool_obj in tools.items():
        fn = getattr(tool_obj, "fn", None)
        if fn is None:
            continue
        tool_obj.fn = watch._wrap(name, fn)


def _patch_low_level_server(server, watch: MCPWatch):
    """Patch a low-level mcp.server.lowlevel.Server by wrapping the
    CallToolRequest dispatcher.

    The low-level Server registers a single handler at
    request_handlers[CallToolRequest] that dispatches to the user's
    @server.call_tool()-registered function. We wrap that handler once
    and extract the per-tool name from the incoming request.
    """
    try:
        from mcp.types import CallToolRequest
    except ImportError:
        return

    handlers = getattr(server, "request_handlers", None)
    if not handlers or CallToolRequest not in handlers:
        return

    original_handler = handlers[CallToolRequest]

    @functools.wraps(original_handler)
    async def wrapped_handler(req):
        tool_name = getattr(getattr(req, "params", None), "name", "unknown")
        start = time.perf_counter()
        error_msg = None
        status = "success"
        try:
            result = await original_handler(req)
            # Low-level Server catches user exceptions and returns them as
            # CallToolResult(isError=True). Inspect result to detect errors,
            # then check for silent failures (empty/null content, no error).
            inner = getattr(result, "root", result)
            if getattr(inner, "isError", False):
                status = "error"
                content = getattr(inner, "content", None) or []
                first = content[0] if content else None
                error_msg = getattr(first, "text", None) or "tool returned isError=True"
                error_msg = error_msg[:500]
            elif watch._is_silent_result(result):
                status = "silent"
            return result
        except Exception as e:
            status = "error"
            error_msg = f"{type(e).__name__}: {str(e)[:500]}"
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            watch._record(tool_name, duration_ms, status, error_msg)

    handlers[CallToolRequest] = wrapped_handler
