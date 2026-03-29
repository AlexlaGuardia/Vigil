"""Vigil Hosted — multi-tenant FastAPI application.

Thin wrapper around the Vigil core. Resolves tenant from API key,
routes to per-tenant SQLite database, meters usage, enforces tier limits.
"""

import os
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from vigil.broadcast import TenantBroadcasters

from vigil.signals import SignalType
from vigil.api import (
    SignalRequest, HandoffRequest, ResumeRequest,
    FocusAddRequest, FrameRegisterRequest,
    KnowledgeSetRequest, TriggerRegisterRequest,
)

from hosted.platform_db import PlatformDB
from hosted.tenant import get_tenant_state
from hosted.config import get_tier_limits, DATA_DIR
from hosted.rate_limit import RateLimiter


# ── Platform DB singleton ────────────────────────────────────────

_platform_db: Optional[PlatformDB] = None


def get_platform_db() -> PlatformDB:
    global _platform_db
    if _platform_db is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _platform_db = PlatformDB()
    return _platform_db


# ── Tenant resolution dependency ─────────────────────────────────

class TenantContext:
    """Resolved tenant context for a request."""
    def __init__(self, project_id: str, account_id: str, tier: str, state: dict):
        self.project_id = project_id
        self.account_id = account_id
        self.tier = tier
        self.state = state


async def resolve_tenant(request: Request) -> TenantContext:
    """Extract API key from request, resolve to tenant context."""
    auth = request.headers.get("Authorization", "")
    key = ""
    if auth.startswith("Bearer "):
        key = auth[7:]
    if not key:
        key = request.headers.get("X-Vigil-Key", "")
    if not key:
        raise HTTPException(401, "Missing API key. Use Authorization: Bearer vgl_xxx")

    pdb = get_platform_db()
    resolved = pdb.resolve_api_key(key)
    if not resolved:
        raise HTTPException(401, "Invalid or revoked API key")

    project_id = resolved["project_id"]
    account_id = resolved["account_id"]
    tier = resolved["tier"]

    state = get_tenant_state(project_id)

    return TenantContext(
        project_id=project_id,
        account_id=account_id,
        tier=tier,
        state=state,
    )


# ── Usage metering dependency ────────────────────────────────────

def check_signal_limit(tenant: TenantContext):
    """Check if tenant has exceeded their signal limit for the month."""
    limits = get_tier_limits(tenant.tier)
    if limits["signal_limit"] == 0:  # unlimited
        return
    pdb = get_platform_db()
    usage = pdb.get_usage(tenant.project_id)
    # 110% soft cap
    if usage["signal_count"] >= int(limits["signal_limit"] * 1.1):
        raise HTTPException(
            429,
            f"Signal limit exceeded ({usage['signal_count']}/{limits['signal_limit']}). "
            f"Upgrade at https://app.vigil-agent.com/dashboard/billing"
        )


def check_rate_limit(tenant: TenantContext, rate_limiter: RateLimiter):
    """Check per-minute rate limit for this tenant's tier."""
    limits = get_tier_limits(tenant.tier)
    rpm = limits.get("rate_limit_per_min", 0)
    allowed, info = rate_limiter.check(tenant.project_id, rpm)
    if not allowed:
        raise HTTPException(
            429,
            detail=f"Rate limit exceeded ({rpm} requests/min). Retry after {info['retry_after']}s.",
            headers={
                "Retry-After": str(info["retry_after"]),
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
            },
        )


# ── App factory ──────────────────────────────────────────────────

def create_hosted_app() -> FastAPI:
    """Create the multi-tenant hosted Vigil API."""

    app = FastAPI(
        title="Vigil Cloud",
        description="Hosted cognitive infrastructure for AI agents",
        version="2.0.0",
    )

    # Mount dashboard routes (auth, UI, key management)
    from hosted.routes_dashboard import router as dashboard_router
    app.include_router(dashboard_router)

    # Mount billing routes (Stripe checkout, portal, webhooks)
    from hosted.billing import router as billing_router
    app.include_router(billing_router)

    # Tenant-scoped WebSocket broadcaster
    _tenant_broadcasters = TenantBroadcasters()

    # Per-tenant rate limiter
    _rate_limiter = RateLimiter(window_seconds=60)

    # ── Background daemon ──────────────────────────────────────

    from hosted.daemon import HostedDaemon
    _daemon = HostedDaemon(get_platform_db(), interval=120, active_window=24)

    @app.on_event("startup")
    async def startup():
        _daemon.start()

    @app.on_event("shutdown")
    async def shutdown():
        _daemon.stop()

    # ── Health (no auth) ─────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "2.0.0", "hosted": True, "daemon": _daemon.stats}

    # ── Core endpoints (tenant-scoped) ───────────────────────

    @app.get("/api/boot")
    async def boot(tenant: TenantContext = Depends(resolve_tenant)):
        return tenant.state["compiler"].boot()

    @app.post("/api/compile")
    async def compile(tenant: TenantContext = Depends(resolve_tenant)):
        check_rate_limit(tenant, _rate_limiter)
        pdb = get_platform_db()
        pdb.increment_usage(tenant.project_id, "compile_count")
        tenant.state["compiler"].synthesize()
        return tenant.state["compiler"].compile()

    @app.post("/api/signal")
    async def signal(req: SignalRequest, tenant: TenantContext = Depends(resolve_tenant)):
        check_rate_limit(tenant, _rate_limiter)
        check_signal_limit(tenant)
        try:
            SignalType(req.signal_type)
        except ValueError:
            valid = [t.value for t in SignalType]
            raise HTTPException(400, f"Invalid signal_type: '{req.signal_type}'. Valid: {valid}")

        sig = tenant.state["bus"].emit(
            from_agent=req.agent,
            content=req.content,
            signal_type=req.signal_type,
            to_agent=req.to_agent,
        )
        # Meter
        pdb = get_platform_db()
        pdb.increment_usage(tenant.project_id, "signal_count")

        # Broadcast to WebSocket clients
        await _tenant_broadcasters.broadcast(tenant.project_id, sig.to_dict())

        # Audit alert-type signals (high-value events)
        if req.signal_type == "alert":
            try:
                tenant.state["db"].audit(
                    actor=req.agent, action="signal.alert",
                    resource_type="signal", resource_id=str(sig.id),
                    detail=req.content[:200],
                )
            except Exception:
                pass

        return {
            "signal_id": sig.id,
            "type": sig.signal_type.value,
            "chars": len(sig.content),
            "budget": sig.signal_type.budget,
        }

    @app.get("/api/status")
    async def status(tenant: TenantContext = Depends(resolve_tenant)):
        awareness = tenant.state["db"].get_awareness()
        if not awareness or not awareness.get("summary"):
            return {"status": "empty", "message": "No awareness compiled yet."}
        return {
            "summary": awareness["summary"],
            "updated_at": awareness.get("updated_at"),
            "updated_by": awareness.get("updated_by"),
        }

    @app.get("/api/signals")
    async def signals(
        hours: int = Query(1, ge=1, le=168),
        limit: int = Query(10, ge=1, le=100),
        agent: str = Query(""),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        sigs = tenant.state["bus"].read(hours=hours, limit=limit)
        if agent:
            sigs = [s for s in sigs if s.from_agent == agent]
        return [s.to_dict() for s in sigs]

    @app.post("/api/handoff")
    async def handoff(req: HandoffRequest, tenant: TenantContext = Depends(resolve_tenant)):
        h = tenant.state["handoff"].end_session(
            agent_id=req.agent,
            summary=req.summary,
            files_touched=req.files_touched,
            decisions=req.decisions,
            next_steps=req.next_steps,
        )
        return {"handoff_id": h.id, "status": "handed_off", "summary_chars": len(req.summary)}

    @app.post("/api/resume")
    async def resume(req: ResumeRequest, tenant: TenantContext = Depends(resolve_tenant)):
        agent = req.agent or "unknown"
        return tenant.state["handoff"].resume(agent)

    @app.get("/api/chain")
    async def chain(
        limit: int = Query(3, ge=1, le=10),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        return {"briefing": tenant.state["handoff"].get_handoff_chain(limit=limit)}

    @app.get("/api/focus")
    async def focus_list(tenant: TenantContext = Depends(resolve_tenant)):
        return tenant.state["db"].get_active_focus(limit=10)

    @app.post("/api/focus")
    async def focus_add(req: FocusAddRequest, tenant: TenantContext = Depends(resolve_tenant)):
        fid = tenant.state["db"].add_focus(
            description=req.description, priority=req.priority, owner=req.owner,
        )
        return {"focus_id": fid, "priority": req.priority, "description": req.description}

    @app.delete("/api/focus/{focus_id}")
    async def focus_complete(focus_id: int, tenant: TenantContext = Depends(resolve_tenant)):
        tenant.state["db"].complete_focus(focus_id)
        return {"focus_id": focus_id, "status": "completed"}

    @app.get("/api/frames")
    async def frames_list(tenant: TenantContext = Depends(resolve_tenant)):
        return tenant.state["db"].get_frames()

    @app.post("/api/frames")
    async def frames_register(req: FrameRegisterRequest, tenant: TenantContext = Depends(resolve_tenant)):
        tenant.state["db"].register_frame(req.frame_id, description=req.description, triggers=req.triggers)
        return {"frame_id": req.frame_id, "triggers": req.triggers, "status": "registered"}

    @app.get("/api/agents")
    async def agents(
        agent: str = Query(""),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        db = tenant.state["db"]
        if agent:
            row = db.query_one(
                "SELECT from_agent, COUNT(*) as signal_count, "
                "MAX(created_at) as last_seen, MIN(created_at) as first_seen "
                "FROM signals WHERE from_agent = ? GROUP BY from_agent",
                (agent,),
            )
            if not row:
                raise HTTPException(404, f"No signals found from agent: {agent}")
            return row
        rows = db.query_all(
            "SELECT from_agent, COUNT(*) as signal_count, MAX(created_at) as last_seen "
            "FROM signals GROUP BY from_agent ORDER BY last_seen DESC"
        )
        return {"agents": rows, "total": len(rows)}

    @app.post("/api/compact")
    async def compact(
        dry_run: bool = Query(False),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        return tenant.state["compactor"].compact(dry_run=dry_run)

    @app.get("/api/triggers")
    async def triggers_list(
        enabled_only: bool = Query(True),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        triggers = tenant.state["triggers"].list_triggers(enabled_only=enabled_only)
        return [t.to_dict() for t in triggers]

    @app.post("/api/triggers")
    async def triggers_register(req: TriggerRegisterRequest, tenant: TenantContext = Depends(resolve_tenant)):
        valid_actions = ["webhook", "signal", "focus", "log"]
        if req.action_type not in valid_actions:
            raise HTTPException(400, f"Invalid action_type: '{req.action_type}'. Valid: {valid_actions}")
        t = tenant.state["triggers"].register(
            name=req.name, action_type=req.action_type, action_config=req.action_config,
            signal_type=req.signal_type, agent_pattern=req.agent_pattern,
            content_pattern=req.content_pattern,
        )
        return t.to_dict()

    @app.delete("/api/triggers/{name}")
    async def triggers_remove(name: str, tenant: TenantContext = Depends(resolve_tenant)):
        tenant.state["triggers"].remove(name)
        return {"name": name, "status": "removed"}

    @app.get("/api/knowledge")
    async def knowledge_list(
        category: str = Query(""),
        agent: str = Query(""),
        limit: int = Query(50, ge=1, le=200),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        kb = tenant.state["knowledge"]
        entries = kb.list(category=category or None, source_agent=agent or None, limit=limit)
        return {"entries": [e.to_dict() for e in entries], "total": kb.count(category=category or None)}

    @app.post("/api/knowledge")
    async def knowledge_set(req: KnowledgeSetRequest, tenant: TenantContext = Depends(resolve_tenant)):
        entry = tenant.state["knowledge"].set(
            key=req.key, value=req.value, category=req.category,
            source_agent=req.source_agent, confidence=req.confidence, metadata=req.metadata,
        )
        return entry.to_dict()

    @app.get("/api/knowledge/{key}")
    async def knowledge_get(key: str, tenant: TenantContext = Depends(resolve_tenant)):
        entry = tenant.state["knowledge"].get(key)
        if not entry:
            raise HTTPException(404, f"No knowledge entry with key: {key}")
        return entry.to_dict()

    @app.delete("/api/knowledge/{key}")
    async def knowledge_delete(key: str, tenant: TenantContext = Depends(resolve_tenant)):
        if not tenant.state["knowledge"].delete(key):
            raise HTTPException(404, f"No knowledge entry with key: {key}")
        return {"key": key, "status": "deleted"}

    @app.get("/api/knowledge/search/{query_str}")
    async def knowledge_recall(
        query_str: str,
        category: str = Query(""),
        limit: int = Query(10, ge=1, le=100),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        results = tenant.state["knowledge"].recall(query_str, category=category or None, limit=limit)
        return [e.to_dict() for e in results]

    @app.get("/api/usage")
    async def usage(tenant: TenantContext = Depends(resolve_tenant)):
        """Get current month's usage for this project."""
        pdb = get_platform_db()
        current = pdb.get_usage(tenant.project_id)
        limits = get_tier_limits(tenant.tier)
        return {
            "tier": tenant.tier,
            "usage": current,
            "limits": {
                "signal_limit": limits["signal_limit"],
                "agent_limit": limits["agent_limit"],
            },
        }

    # ── Audit Log (tenant-scoped) ───────────────────────────

    @app.get("/api/audit")
    async def audit_log(
        limit: int = Query(50, ge=1, le=200),
        actor: str = Query(""),
        action: str = Query(""),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        """Get audit log entries for this project."""
        entries = tenant.state["db"].get_audit_log(limit=limit, actor=actor, action=action)
        return {"entries": entries, "count": len(entries)}

    # ── MCP Observability (tenant-scoped) ─────────────────────

    @app.get("/api/mcp/health")
    async def mcp_health(
        server: str = Query(""),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        """MCP server health for this tenant."""
        db = tenant.state["db"]
        if server:
            servers = [server]
        else:
            rows = db.query_all("SELECT DISTINCT server_name FROM mcp_events ORDER BY server_name")
            servers = [r["server_name"] for r in rows]

        if not servers:
            return {"servers": [], "message": "No MCP events yet. Use `from vigil.mcpwatch import instrument` to start monitoring."}

        result = []
        for srv in servers:
            stats = db.query_one(
                "SELECT COUNT(*) as total_calls, "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as total_errors, "
                "AVG(duration_ms) as avg_ms, MAX(duration_ms) as max_ms, "
                "MIN(created_at) as first_seen, MAX(created_at) as last_seen "
                "FROM mcp_events WHERE server_name = ?", (srv,),
            )
            tools = db.query_all(
                "SELECT tool_name, COUNT(*) as calls, "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors, "
                "AVG(duration_ms) as avg_ms, MAX(duration_ms) as max_ms "
                "FROM mcp_events WHERE server_name = ? AND created_at > datetime('now', '-24 hours') "
                "GROUP BY tool_name ORDER BY calls DESC", (srv,),
            )
            total = stats["total_calls"] or 0
            errors = stats["total_errors"] or 0
            error_rate = errors / total if total else 0
            result.append({
                "server": srv,
                "status": "unhealthy" if error_rate > 0.5 else ("degraded" if error_rate > 0.1 else "healthy"),
                "total_calls": total, "total_errors": errors,
                "error_rate": round(error_rate, 4),
                "avg_ms": round(stats["avg_ms"] or 0, 2),
                "last_seen": stats["last_seen"],
                "tools_24h": tools,
            })
        return {"servers": result}

    @app.get("/api/mcp/errors")
    async def mcp_errors(
        server: str = Query(""),
        limit: int = Query(50, ge=1, le=200),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        """Recent MCP tool errors for this tenant."""
        db = tenant.state["db"]
        if server:
            rows = db.query_all(
                "SELECT server_name, tool_name, duration_ms, error, created_at "
                "FROM mcp_events WHERE status='error' AND server_name=? ORDER BY created_at DESC LIMIT ?",
                (server, limit),
            )
        else:
            rows = db.query_all(
                "SELECT server_name, tool_name, duration_ms, error, created_at "
                "FROM mcp_events WHERE status='error' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return {"errors": rows, "count": len(rows)}

    @app.get("/api/mcp/latency")
    async def mcp_latency(
        server: str = Query(""),
        hours: int = Query(24, ge=1, le=168),
        tenant: TenantContext = Depends(resolve_tenant),
    ):
        """Latency percentiles for this tenant."""
        db = tenant.state["db"]
        params = [f"-{hours} hours"]
        q = "SELECT duration_ms FROM mcp_events WHERE created_at > datetime('now', ?) "
        if server:
            q += "AND server_name = ? "
            params.append(server)
        q += "ORDER BY duration_ms"
        rows = db.query_all(q, tuple(params))
        if not rows:
            return {"p50": 0, "p95": 0, "p99": 0, "count": 0, "hours": hours}
        durations = [r["duration_ms"] for r in rows]
        n = len(durations)
        return {
            "p50": round(durations[int(n * 0.50)], 2),
            "p95": round(durations[int(n * 0.95)], 2),
            "p99": round(durations[min(int(n * 0.99), n - 1)], 2),
            "count": n, "hours": hours,
        }

    # ── WebSocket (tenant-scoped) ────────────────────────────

    @app.websocket("/ws/signals")
    async def ws_signals(websocket: WebSocket, key: str = "", agent: str = ""):
        """Real-time signal stream via WebSocket.

        Connect: wss://app.vigil-agent.com/ws/signals?key=vgl_xxx&agent=my-agent
        Sends JSON signal objects as they're emitted.
        """
        if not key:
            await websocket.close(code=4001, reason="Missing API key")
            return

        pdb = get_platform_db()
        resolved = pdb.resolve_api_key(key)
        if not resolved:
            await websocket.close(code=4001, reason="Invalid API key")
            return

        project_id = resolved["project_id"]
        broadcaster = _tenant_broadcasters.get(project_id)
        await broadcaster.connect(websocket, agent_filter=agent)

        try:
            # Send recent signals as initial payload
            state = get_tenant_state(project_id)
            recent = state["bus"].read(hours=1, limit=10)
            if agent:
                recent = [s for s in recent if s.from_agent == agent]
            for s in recent:
                await websocket.send_json(s.to_dict())

            # Keep alive
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await broadcaster.disconnect(websocket)

    return app
