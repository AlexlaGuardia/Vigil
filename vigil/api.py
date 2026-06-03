"""
Vigil REST API — HTTP service for persistent agent awareness.

Agents can connect from anywhere over HTTP. Shares the same data path
as the MCP server and CLI — all three write to the same SQLite DB.

Usage:
    vigil serve --transport http --port 8300

    # Or programmatic
    from vigil.api import create_app
    app = create_app("vigil.db")
    uvicorn.run(app, host="0.0.0.0", port=8300)

Auth:
    Set VIGIL_API_KEY env var to require Bearer token auth.
    If unset, no auth (local dev mode).
"""

import json
import os
from typing import Optional, List

from pathlib import Path as FilePath

from fastapi import FastAPI, HTTPException, Depends, Request, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from vigil.broadcast import SignalBroadcaster

from vigil.db import VigilDB
from vigil.signals import SignalBus, SignalType
from vigil.frames import FrameDetector
from vigil.awareness import AwarenessCompiler
from vigil.handoff import HandoffProtocol
from vigil.compaction import SignalCompactor
from vigil.triggers import TriggerEngine
from vigil.knowledge import KnowledgeBase


# ── Request/Response models ───────────────────────────────────────

class SignalRequest(BaseModel):
    agent: str
    content: str
    signal_type: str = "observation"
    to_agent: Optional[str] = None


class HandoffRequest(BaseModel):
    agent: str
    summary: str
    files_touched: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)


class ResumeRequest(BaseModel):
    agent: str = ""


class FocusAddRequest(BaseModel):
    description: str
    priority: int = 5
    owner: Optional[str] = None


class FrameRegisterRequest(BaseModel):
    frame_id: str
    description: str = ""
    triggers: List[str] = Field(default_factory=list)


class KnowledgeSetRequest(BaseModel):
    key: str
    value: str
    category: str = "general"
    source_agent: Optional[str] = None
    confidence: float = 1.0
    metadata: dict = Field(default_factory=dict)


class TriggerRegisterRequest(BaseModel):
    name: str
    action_type: str  # webhook, signal, focus, log
    action_config: dict = Field(default_factory=dict)
    signal_type: Optional[str] = None
    agent_pattern: str = "*"
    content_pattern: Optional[str] = None


# ── App factory ───────────────────────────────────────────────────

def build_state(db_path: str = "vigil.db", default_frame: str = "default") -> dict:
    """Build a Vigil state dict from a database path. Reusable by hosted tier."""
    db = VigilDB(db_path)
    return {
        "db": db,
        "bus": SignalBus(db),
        "frames": FrameDetector(db, default_frame=default_frame),
        "compiler": AwarenessCompiler(db, frame_detector=FrameDetector(db, default_frame=default_frame)),
        "handoff": HandoffProtocol(db),
        "compactor": SignalCompactor(db),
        "triggers": TriggerEngine(db, SignalBus(db)),
        "knowledge": KnowledgeBase(db),
    }


def create_app(
    db_path: str = "vigil.db",
    default_frame: str = "default",
    api_key: Optional[str] = None,
    state: Optional[dict] = None,
) -> FastAPI:
    """
    Create a Vigil REST API application.

    Args:
        db_path: Path to Vigil SQLite database
        default_frame: Default frame when no triggers match
        api_key: API key for auth (None = no auth). Also reads VIGIL_API_KEY env var.
        state: Pre-built state dict (for hosted multi-tenant use). Overrides db_path.
    """
    key = api_key or os.environ.get("VIGIL_API_KEY")

    if state is None:
        state = build_state(db_path, default_frame)

    # Signal broadcaster for WebSocket clients
    broadcaster = SignalBroadcaster()
    state["broadcaster"] = broadcaster

    app = FastAPI(
        title="Vigil",
        description="Cognitive infrastructure for AI agents",
        version="1.5.0",
    )

    # ── Templates & static files ──────────────────────────────

    _pkg_dir = FilePath(__file__).parent
    _templates_dir = _pkg_dir / "templates"
    _static_dir = _pkg_dir / "static"

    templates = Jinja2Templates(directory=str(_templates_dir)) if _templates_dir.exists() else None

    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    # ── Dashboard routes ──────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Main dashboard — live overview."""
        if not templates:
            return HTMLResponse("<h1>Vigil</h1><p>Dashboard templates not found. Use the API at <a href='/docs'>/docs</a>.</p>")
        ctx = state["compiler"].boot()
        awareness = state["db"].get_awareness()
        focus = state["db"].get_active_focus(limit=10)
        recent = state["bus"].read(hours=1, limit=20)
        agents_rows = state["db"].query_all(
            "SELECT from_agent, COUNT(*) as signal_count, MAX(created_at) as last_seen "
            "FROM signals GROUP BY from_agent ORDER BY last_seen DESC LIMIT 10"
        )
        return templates.TemplateResponse(request, "index.html", {
            "frame": ctx.get("frame", "default"),
            "awareness": awareness.get("summary", "") if awareness else "",
            "awareness_updated": awareness.get("updated_at", "") if awareness else "",
            "focus": focus,
            "signals": [s.to_dict() for s in recent],
            "agents": agents_rows,
            "compiled_at": ctx.get("compiled_at", ""),
        })

    @app.get("/dashboard/agents", response_class=HTMLResponse)
    async def dashboard_agents(request: Request):
        """Agents page."""
        if not templates:
            return HTMLResponse("Templates not found.")
        agents_rows = state["db"].query_all(
            "SELECT from_agent, COUNT(*) as signal_count, MAX(created_at) as last_seen, "
            "MIN(created_at) as first_seen FROM signals GROUP BY from_agent ORDER BY last_seen DESC"
        )
        for a in agents_rows:
            sessions = state["db"].query_all(
                "SELECT summary, started_at, ended_at FROM sessions "
                "WHERE agent_id = ? ORDER BY started_at DESC LIMIT 3",
                (a["from_agent"],),
            )
            a["sessions"] = sessions
        return templates.TemplateResponse(request, "agents.html", {"agents": agents_rows})

    @app.get("/dashboard/signals", response_class=HTMLResponse)
    async def dashboard_signals(request: Request, hours: int = Query(6, ge=1, le=168)):
        """Signals timeline page."""
        if not templates:
            return HTMLResponse("Templates not found.")
        recent = state["bus"].read(hours=hours, limit=100)
        return templates.TemplateResponse(request, "signals.html", {
            "signals": [s.to_dict() for s in recent],
            "hours": hours,
        })

    @app.get("/dashboard/handoffs", response_class=HTMLResponse)
    async def dashboard_handoffs(request: Request):
        """Handoff chain page."""
        if not templates:
            return HTMLResponse("Templates not found.")
        handoffs = state["db"].query_all(
            "SELECT * FROM handoffs ORDER BY ended_at DESC LIMIT 20"
        )
        from vigil.handoff import _parse_json_list
        for h in handoffs:
            h["files_touched"] = _parse_json_list(h.get("files_touched"))
            h["decisions"] = _parse_json_list(h.get("decisions"))
            h["next_steps"] = _parse_json_list(h.get("next_steps"))
        return templates.TemplateResponse(request, "handoffs.html", {"handoffs": handoffs})

    @app.get("/dashboard/frames", response_class=HTMLResponse)
    async def dashboard_frames(request: Request):
        """Frames map page."""
        if not templates:
            return HTMLResponse("Templates not found.")
        frames = state["db"].get_frames()
        current = state["compiler"].boot().get("frame", "default")
        return templates.TemplateResponse(request, "frames.html", {
            "frames": frames,
            "current_frame": current,
        })

    # ── htmx partials (for live updates) ──────────────────────

    @app.get("/partials/signals", response_class=HTMLResponse)
    async def partial_signals(request: Request):
        """Signal list partial — htmx polls this for live updates."""
        if not templates:
            return HTMLResponse("")
        recent = state["bus"].read(hours=1, limit=20)
        return templates.TemplateResponse(request, "partials/signal_list.html", {
            "signals": [s.to_dict() for s in recent],
        })

    @app.get("/partials/awareness", response_class=HTMLResponse)
    async def partial_awareness(request: Request):
        """Awareness partial — htmx polls this."""
        if not templates:
            return HTMLResponse("")
        awareness = state["db"].get_awareness()
        return templates.TemplateResponse(request, "partials/awareness.html", {
            "awareness": awareness.get("summary", "") if awareness else "",
            "awareness_updated": awareness.get("updated_at", "") if awareness else "",
        })

    # ── Auth dependency ───────────────────────────────────────

    async def verify_key(request: Request):
        if not key:
            return
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {key}":
            return
        header_key = request.headers.get("X-Vigil-Key", "")
        if header_key == key:
            return
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # ── Endpoints ─────────────────────────────────────────────

    @app.get("/boot", dependencies=[Depends(verify_key)])
    async def boot():
        """Boot with pre-compiled hot context."""
        return state["compiler"].boot()

    @app.post("/compile", dependencies=[Depends(verify_key)])
    async def compile():
        """Force a fresh awareness compilation."""
        state["compiler"].synthesize()
        return state["compiler"].compile()

    @app.post("/signal", dependencies=[Depends(verify_key)])
    async def signal(req: SignalRequest):
        """Emit a signal from an agent."""
        try:
            SignalType(req.signal_type)
        except ValueError:
            valid = [t.value for t in SignalType]
            raise HTTPException(400, f"Invalid signal_type: '{req.signal_type}'. Valid: {valid}")

        sig = state["bus"].emit(
            from_agent=req.agent,
            content=req.content,
            signal_type=req.signal_type,
            to_agent=req.to_agent,
        )

        # Broadcast to WebSocket clients
        await broadcaster.broadcast(sig.to_dict())

        return {
            "signal_id": sig.id,
            "type": sig.signal_type.value,
            "chars": len(sig.content),
            "budget": sig.signal_type.budget,
        }

    @app.get("/status", dependencies=[Depends(verify_key)])
    async def status():
        """Get current awareness state."""
        awareness = state["db"].get_awareness()
        if not awareness or not awareness.get("summary"):
            return {"status": "empty", "message": "No awareness compiled yet."}
        return {
            "summary": awareness["summary"],
            "updated_at": awareness.get("updated_at"),
            "updated_by": awareness.get("updated_by"),
        }

    @app.get("/signals", dependencies=[Depends(verify_key)])
    async def signals(
        hours: int = Query(1, ge=1, le=168),
        limit: int = Query(10, ge=1, le=100),
        agent: str = Query(""),
    ):
        """Read recent signals."""
        sigs = state["bus"].read(hours=hours, limit=limit)
        if agent:
            sigs = [s for s in sigs if s.from_agent == agent]
        return [s.to_dict() for s in sigs]

    @app.post("/handoff", dependencies=[Depends(verify_key)])
    async def handoff(req: HandoffRequest):
        """End a session with a structured handoff."""
        h = state["handoff"].end_session(
            agent_id=req.agent,
            summary=req.summary,
            files_touched=req.files_touched,
            decisions=req.decisions,
            next_steps=req.next_steps,
        )
        return {
            "handoff_id": h.id,
            "status": "handed_off",
            "summary_chars": len(req.summary),
        }

    @app.post("/resume", dependencies=[Depends(verify_key)])
    async def resume(req: ResumeRequest):
        """Resume from the last session's handoff."""
        agent = req.agent or "unknown"
        return state["handoff"].resume(agent)

    @app.get("/chain", dependencies=[Depends(verify_key)])
    async def chain(limit: int = Query(3, ge=1, le=10)):
        """Get a briefing of the last N handoffs."""
        return {"briefing": state["handoff"].get_handoff_chain(limit=limit)}

    @app.get("/stale", dependencies=[Depends(verify_key)])
    async def stale(minutes: int = Query(30, ge=1)):
        """Find agents with open sessions that have gone silent."""
        result = state["handoff"].auto_detect_stale(minutes=minutes)
        return {"stale_sessions": result, "threshold_minutes": minutes}

    @app.get("/focus", dependencies=[Depends(verify_key)])
    async def focus_list():
        """List active focus items."""
        return state["db"].get_active_focus(limit=10)

    @app.post("/focus", dependencies=[Depends(verify_key)])
    async def focus_add(req: FocusAddRequest):
        """Add a focus item."""
        fid = state["db"].add_focus(
            description=req.description,
            priority=req.priority,
            owner=req.owner,
        )
        return {"focus_id": fid, "priority": req.priority, "description": req.description}

    @app.delete("/focus/{focus_id}", dependencies=[Depends(verify_key)])
    async def focus_complete(focus_id: int):
        """Complete a focus item."""
        state["db"].complete_focus(focus_id)
        return {"focus_id": focus_id, "status": "completed"}

    @app.get("/frames", dependencies=[Depends(verify_key)])
    async def frames_list():
        """List registered frames."""
        return state["db"].get_frames()

    @app.post("/frames", dependencies=[Depends(verify_key)])
    async def frames_register(req: FrameRegisterRequest):
        """Register a new frame."""
        state["db"].register_frame(req.frame_id, description=req.description, triggers=req.triggers)
        return {"frame_id": req.frame_id, "triggers": req.triggers, "status": "registered"}

    @app.get("/agents", dependencies=[Depends(verify_key)])
    async def agents(agent: str = Query("")):
        """List known agents and their activity."""
        db = state["db"]
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
        else:
            rows = db.query_all(
                "SELECT from_agent, COUNT(*) as signal_count, "
                "MAX(created_at) as last_seen "
                "FROM signals GROUP BY from_agent ORDER BY last_seen DESC"
            )
            return {"agents": rows, "total": len(rows)}

    @app.post("/compact", dependencies=[Depends(verify_key)])
    async def compact(dry_run: bool = Query(False)):
        """Run signal compaction."""
        return state["compactor"].compact(dry_run=dry_run)

    @app.get("/events", dependencies=[Depends(verify_key)])
    async def events(agent: str = Query("")):
        """SSE stream of new signals. Long-polls every 2 seconds."""
        import asyncio

        last_id = 0

        async def stream():
            nonlocal last_id
            # Get current max signal ID as starting point
            row = state["db"].query_one("SELECT MAX(id) as max_id FROM signals")
            if row and row["max_id"]:
                last_id = row["max_id"]

            while True:
                query = "SELECT id, from_agent, signal_type, content, created_at FROM signals WHERE id > ?"
                params = [last_id]
                if agent:
                    query += " AND from_agent = ?"
                    params.append(agent)
                query += " ORDER BY id ASC LIMIT 20"

                rows = state["db"].query_all(query, tuple(params))
                for row in rows:
                    last_id = row["id"]
                    data = json.dumps(row, default=str)
                    yield f"data: {data}\n\n"

                await asyncio.sleep(2)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.websocket("/ws/signals")
    async def ws_signals(websocket: WebSocket, agent: str = ""):
        """WebSocket stream of real-time signals.

        Connect: ws://host:port/ws/signals?agent=my-agent
        Auth: Pass API key as query param ?key=xxx or first message {"key": "xxx"}

        Messages are JSON signal objects pushed as they're emitted.
        """
        # Auth check
        ws_key = websocket.query_params.get("key", "")
        if key and ws_key != key:
            # Wait for auth message
            await websocket.accept()
            try:
                auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5)
                if auth_msg.get("key") != key:
                    await websocket.send_json({"error": "Invalid API key"})
                    await websocket.close(code=4001)
                    return
            except Exception:
                await websocket.close(code=4001)
                return
            agent_filter = auth_msg.get("agent", agent)
            await broadcaster.connect(websocket, agent_filter=agent_filter)
        else:
            await broadcaster.connect(websocket, agent_filter=agent)

        try:
            # Send recent signals as initial payload
            recent = state["bus"].read(hours=1, limit=10)
            if agent:
                recent = [s for s in recent if s.from_agent == agent]
            for s in recent:
                await websocket.send_json(s.to_dict())

            # Keep connection alive — wait for disconnect
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    # Send ping to keep alive
                    await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await broadcaster.disconnect(websocket)

    @app.get("/triggers", dependencies=[Depends(verify_key)])
    async def triggers_list(enabled_only: bool = Query(True)):
        """List registered triggers."""
        triggers = state["triggers"].list_triggers(enabled_only=enabled_only)
        return [t.to_dict() for t in triggers]

    @app.post("/triggers", dependencies=[Depends(verify_key)])
    async def triggers_register(req: TriggerRegisterRequest):
        """Register a new trigger."""
        valid_actions = ["webhook", "signal", "focus", "log"]
        if req.action_type not in valid_actions:
            raise HTTPException(400, f"Invalid action_type: '{req.action_type}'. Valid: {valid_actions}")
        t = state["triggers"].register(
            name=req.name,
            action_type=req.action_type,
            action_config=req.action_config,
            signal_type=req.signal_type,
            agent_pattern=req.agent_pattern,
            content_pattern=req.content_pattern,
        )
        return t.to_dict()

    @app.delete("/triggers/{name}", dependencies=[Depends(verify_key)])
    async def triggers_remove(name: str):
        """Remove a trigger."""
        state["triggers"].remove(name)
        return {"name": name, "status": "removed"}

    @app.get("/knowledge", dependencies=[Depends(verify_key)])
    async def knowledge_list(
        category: str = Query(""),
        agent: str = Query(""),
        limit: int = Query(50, ge=1, le=200),
    ):
        """List knowledge entries."""
        kb = state["knowledge"]
        entries = kb.list(
            category=category or None,
            source_agent=agent or None,
            limit=limit,
        )
        return {
            "entries": [e.to_dict() for e in entries],
            "total": kb.count(category=category or None),
        }

    @app.post("/knowledge", dependencies=[Depends(verify_key)])
    async def knowledge_set(req: KnowledgeSetRequest):
        """Store or update a knowledge entry."""
        kb = state["knowledge"]
        entry = kb.set(
            key=req.key,
            value=req.value,
            category=req.category,
            source_agent=req.source_agent,
            confidence=req.confidence,
            metadata=req.metadata,
        )
        return entry.to_dict()

    @app.get("/knowledge/{key}", dependencies=[Depends(verify_key)])
    async def knowledge_get(key: str):
        """Get a specific knowledge entry."""
        kb = state["knowledge"]
        entry = kb.get(key)
        if not entry:
            raise HTTPException(404, f"No knowledge entry with key: {key}")
        return entry.to_dict()

    @app.delete("/knowledge/{key}", dependencies=[Depends(verify_key)])
    async def knowledge_delete(key: str):
        """Delete a knowledge entry."""
        kb = state["knowledge"]
        if not kb.delete(key):
            raise HTTPException(404, f"No knowledge entry with key: {key}")
        return {"key": key, "status": "deleted"}

    @app.get("/knowledge/search/{query}", dependencies=[Depends(verify_key)])
    async def knowledge_recall(
        query: str,
        category: str = Query(""),
        limit: int = Query(10, ge=1, le=100),
    ):
        """Fuzzy-search knowledge entries."""
        kb = state["knowledge"]
        results = kb.recall(query, category=category or None, limit=limit)
        return [e.to_dict() for e in results]

    # ── MCP Observability endpoints ─────────────────────────────

    @app.get("/mcp/health", dependencies=[Depends(verify_key)])
    async def mcp_health(server: str = Query("", description="Filter by server name")):
        """MCP server health summary — call volume, error rates, latency."""
        db = state["db"]
        # Get all monitored servers or filter
        if server:
            servers = [server]
        else:
            rows = db.query_all(
                "SELECT DISTINCT server_name FROM mcp_events ORDER BY server_name"
            )
            servers = [r["server_name"] for r in rows]

        if not servers:
            return {"servers": [], "message": "No MCP events recorded yet. Instrument a server with `from vigil.mcpwatch import instrument`."}

        result = []
        for srv in servers:
            stats = db.query_one(
                "SELECT COUNT(*) as total_calls, "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as total_errors, "
                "SUM(CASE WHEN status='silent' THEN 1 ELSE 0 END) as total_silent, "
                "AVG(duration_ms) as avg_ms, "
                "MAX(duration_ms) as max_ms, "
                "MIN(created_at) as first_seen, "
                "MAX(created_at) as last_seen "
                "FROM mcp_events WHERE server_name = ?",
                (srv,),
            )
            # Get per-tool breakdown
            tools = db.query_all(
                "SELECT tool_name, COUNT(*) as calls, "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors, "
                "SUM(CASE WHEN status='silent' THEN 1 ELSE 0 END) as silent, "
                "AVG(duration_ms) as avg_ms, MAX(duration_ms) as max_ms "
                "FROM mcp_events WHERE server_name = ? "
                "AND created_at > datetime('now', '-24 hours') "
                "GROUP BY tool_name ORDER BY calls DESC",
                (srv,),
            )
            total = stats["total_calls"] or 0
            errors = stats["total_errors"] or 0
            silent = stats["total_silent"] or 0
            error_rate = errors / total if total else 0
            silent_rate = silent / total if total else 0

            if error_rate > 0.5 or silent_rate > 0.5:
                status = "unhealthy"
            elif error_rate > 0.1 or silent_rate > 0.1:
                status = "degraded"
            else:
                status = "healthy"

            result.append({
                "server": srv,
                "status": status,
                "total_calls": total,
                "total_errors": errors,
                "error_rate": round(error_rate, 4),
                "total_silent": silent,
                "silent_rate": round(silent_rate, 4),
                "avg_ms": round(stats["avg_ms"] or 0, 2),
                "max_ms": round(stats["max_ms"] or 0, 2),
                "first_seen": stats["first_seen"],
                "last_seen": stats["last_seen"],
                "tools_24h": tools,
            })

        return {"servers": result}

    @app.get("/mcp/tools", dependencies=[Depends(verify_key)])
    async def mcp_tools(
        server: str = Query(""),
        hours: int = Query(24, ge=1, le=168),
    ):
        """Per-tool analytics — call counts, error rates, latency."""
        db = state["db"]
        params = [f"-{hours} hours"]
        query = (
            "SELECT server_name, tool_name, COUNT(*) as calls, "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors, "
            "AVG(duration_ms) as avg_ms, "
            "MIN(duration_ms) as min_ms, "
            "MAX(duration_ms) as max_ms "
            "FROM mcp_events WHERE created_at > datetime('now', ?) "
        )
        if server:
            query += "AND server_name = ? "
            params.append(server)
        query += "GROUP BY server_name, tool_name ORDER BY calls DESC"
        rows = db.query_all(query, tuple(params))

        for r in rows:
            r["error_rate"] = round(r["errors"] / r["calls"], 4) if r["calls"] else 0
            r["avg_ms"] = round(r["avg_ms"] or 0, 2)
            r["min_ms"] = round(r["min_ms"] or 0, 2)
            r["max_ms"] = round(r["max_ms"] or 0, 2)
        return {"tools": rows, "hours": hours}

    @app.get("/mcp/errors", dependencies=[Depends(verify_key)])
    async def mcp_errors(
        server: str = Query(""),
        limit: int = Query(50, ge=1, le=200),
    ):
        """Recent MCP tool errors."""
        db = state["db"]
        if server:
            rows = db.query_all(
                "SELECT server_name, tool_name, duration_ms, error, created_at "
                "FROM mcp_events WHERE status = 'error' AND server_name = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (server, limit),
            )
        else:
            rows = db.query_all(
                "SELECT server_name, tool_name, duration_ms, error, created_at "
                "FROM mcp_events WHERE status = 'error' "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return {"errors": rows, "count": len(rows)}

    @app.get("/mcp/silent", dependencies=[Depends(verify_key)])
    async def mcp_silent(
        server: str = Query(""),
        limit: int = Query(50, ge=1, le=200),
    ):
        """Recent MCP silent failures — calls that returned empty/null content
        with no error raised. The failure mode generic monitors miss."""
        db = state["db"]
        if server:
            rows = db.query_all(
                "SELECT server_name, tool_name, duration_ms, created_at "
                "FROM mcp_events WHERE status = 'silent' AND server_name = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (server, limit),
            )
        else:
            rows = db.query_all(
                "SELECT server_name, tool_name, duration_ms, created_at "
                "FROM mcp_events WHERE status = 'silent' "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return {"silent_failures": rows, "count": len(rows)}

    @app.get("/mcp/latency", dependencies=[Depends(verify_key)])
    async def mcp_latency(
        server: str = Query(""),
        hours: int = Query(24, ge=1, le=168),
    ):
        """Latency percentiles over time."""
        db = state["db"]
        params = [f"-{hours} hours"]
        query = (
            "SELECT duration_ms FROM mcp_events WHERE created_at > datetime('now', ?) "
        )
        if server:
            query += "AND server_name = ? "
            params.append(server)
        query += "ORDER BY duration_ms"
        rows = db.query_all(query, tuple(params))

        if not rows:
            return {"p50": 0, "p95": 0, "p99": 0, "count": 0, "hours": hours}

        durations = [r["duration_ms"] for r in rows]
        n = len(durations)
        return {
            "p50": round(durations[int(n * 0.50)], 2),
            "p95": round(durations[int(n * 0.95)], 2),
            "p99": round(durations[min(int(n * 0.99), n - 1)], 2),
            "count": n,
            "hours": hours,
        }

    @app.get("/mcp/volume", dependencies=[Depends(verify_key)])
    async def mcp_volume(
        server: str = Query(""),
        hours: int = Query(24, ge=1, le=168),
    ):
        """Call volume over time (hourly buckets)."""
        db = state["db"]
        params = [f"-{hours} hours"]
        query = (
            "SELECT strftime('%Y-%m-%d %H:00', created_at) as bucket, "
            "COUNT(*) as calls, "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors, "
            "SUM(CASE WHEN status='silent' THEN 1 ELSE 0 END) as silent, "
            "AVG(duration_ms) as avg_ms "
            "FROM mcp_events WHERE created_at > datetime('now', ?) "
        )
        if server:
            query += "AND server_name = ? "
            params.append(server)
        query += "GROUP BY bucket ORDER BY bucket"
        rows = db.query_all(query, tuple(params))

        for r in rows:
            r["avg_ms"] = round(r["avg_ms"] or 0, 2)
        return {"buckets": rows, "hours": hours}

    # ── Audit Log ──────────────────────────────────────────────

    @app.get("/audit", dependencies=[Depends(verify_key)])
    async def audit_log(
        limit: int = Query(50, ge=1, le=200),
        actor: str = Query(""),
        action: str = Query(""),
    ):
        """Get audit log entries."""
        entries = state["db"].get_audit_log(limit=limit, actor=actor, action=action)
        return {"entries": entries, "count": len(entries)}

    @app.get("/health")
    async def health():
        """Health check — no auth required."""
        return {"status": "ok", "version": "2.2.0"}

    return app


# ── Entry point ───────────────────────────────────────────────────

def run_http(
    db_path: str = "vigil.db",
    default_frame: str = "default",
    host: str = "127.0.0.1",
    port: int = 8300,
):
    """Run the Vigil REST API server."""
    import uvicorn
    app = create_app(db_path=db_path, default_frame=default_frame)
    uvicorn.run(app, host=host, port=port)
