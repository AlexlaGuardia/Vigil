"""Dashboard routes — auth, project overview, API key management."""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

from hosted.auth import (
    get_login_url, exchange_code, create_session_cookie,
    read_session_cookie, get_current_user, SESSION_COOKIE,
)
from hosted.platform_db import PlatformDB
from hosted.config import APP_URL, get_tier_limits

router = APIRouter()


def _require_user(request: Request, pdb: PlatformDB) -> dict:
    """Get current user or redirect to login."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    account_id = read_session_cookie(cookie)
    if not account_id:
        return None
    return pdb.get_account(account_id)


# ── Auth routes ──────────────────────────────────────────────

@router.get("/auth/login")
async def login(request: Request):
    """Redirect to GitHub OAuth."""
    url, state = get_login_url()
    response = RedirectResponse(url)
    response.set_cookie("oauth_state", state, max_age=600, httponly=True, secure=True, samesite="lax")
    return response


@router.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    """Handle GitHub OAuth callback."""
    if not code:
        raise HTTPException(400, "Missing OAuth code")

    # Verify state
    saved_state = request.cookies.get("oauth_state", "")
    if not saved_state or saved_state != state:
        raise HTTPException(400, "Invalid OAuth state")

    # Exchange code for user info
    github_user = await exchange_code(code)

    # Create or update account
    from hosted.app import get_platform_db
    pdb = get_platform_db()
    account = pdb.create_account(
        github_id=github_user["github_id"],
        email=github_user["email"],
        name=github_user["name"],
        avatar_url=github_user["avatar_url"],
    )

    # Auto-create first project if none exist
    projects = pdb.get_projects(account["id"])
    if not projects:
        pdb.create_project(account["id"], "My Project")

    # Set session cookie and redirect to dashboard
    session_value = create_session_cookie(account["id"])
    response = RedirectResponse(f"{APP_URL}/dashboard", status_code=302)
    response.set_cookie(
        SESSION_COOKIE, session_value,
        max_age=60 * 60 * 24 * 30,  # 30 days
        httponly=True, secure=True, samesite="lax",
    )
    response.delete_cookie("oauth_state")
    return response


@router.get("/auth/logout")
async def logout():
    """Clear session and redirect to landing page."""
    response = RedirectResponse("https://vigil-agent.com")
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── Dashboard routes ─────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — project overview + usage."""
    from hosted.app import get_platform_db
    pdb = get_platform_db()
    user = _require_user(request, pdb)
    if not user:
        return RedirectResponse("/auth/login")

    projects = pdb.get_projects(user["id"])
    project = projects[0] if projects else None
    usage = pdb.get_usage(project["id"]) if project else {"signal_count": 0, "compile_count": 0}
    limits = get_tier_limits(user["tier"])
    keys = pdb.get_api_keys(project["id"]) if project else []

    usage_pct = 0
    if limits["signal_limit"] > 0:
        usage_pct = min(100, int(usage["signal_count"] / limits["signal_limit"] * 100))

    # Fetch additional analytics data
    agents_data = []
    mcp_servers_data = []
    signal_volume = []
    if project:
        from hosted.tenant import get_tenant_state
        try:
            tenant_state = get_tenant_state(project["id"])
            tdb = tenant_state["db"]

            # Agent activity
            agents_data = tdb.query_all(
                "SELECT from_agent, COUNT(*) as signal_count, "
                "MAX(created_at) as last_seen, MIN(created_at) as first_seen "
                "FROM signals GROUP BY from_agent ORDER BY last_seen DESC LIMIT 10"
            )

            # MCP server health
            mcp_servers_data = []
            mcp_srvs = tdb.query_all("SELECT DISTINCT server_name FROM mcp_events ORDER BY server_name")
            for srv_row in mcp_srvs:
                srv = srv_row["server_name"]
                stats = tdb.query_one(
                    "SELECT COUNT(*) as total_calls, "
                    "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as total_errors, "
                    "AVG(duration_ms) as avg_ms, MAX(created_at) as last_seen "
                    "FROM mcp_events WHERE server_name = ? AND created_at > datetime('now', '-24 hours')",
                    (srv,),
                )
                total = stats["total_calls"] or 0
                errors = stats["total_errors"] or 0
                error_rate = errors / total if total else 0
                status_label = "unhealthy" if error_rate > 0.5 else ("degraded" if error_rate > 0.1 else "healthy")
                mcp_servers_data.append({
                    "name": srv, "status": status_label,
                    "calls": total, "errors": errors,
                    "avg_ms": round(stats["avg_ms"] or 0, 1),
                    "last_seen": stats["last_seen"],
                })

            # Signal volume — last 7 days, daily buckets
            signal_volume = tdb.query_all(
                "SELECT strftime('%Y-%m-%d', created_at) as day, COUNT(*) as count "
                "FROM signals WHERE created_at > datetime('now', '-7 days') "
                "GROUP BY day ORDER BY day"
            )

            # Signal type distribution
            signal_types = tdb.query_all(
                "SELECT signal_type, COUNT(*) as count FROM signals "
                "WHERE created_at > datetime('now', '-7 days') "
                "GROUP BY signal_type ORDER BY count DESC"
            )

            # Hourly volume — last 24h for bar chart
            hourly_volume = tdb.query_all(
                "SELECT strftime('%H', created_at) as hour, COUNT(*) as count "
                "FROM signals WHERE created_at > datetime('now', '-24 hours') "
                "GROUP BY hour ORDER BY hour"
            )
        except Exception:
            signal_types = []
            hourly_volume = []

    # Get first API key prefix for WebSocket connection
    ws_key = ""
    if keys:
        # We need the actual key prefix for the WS URL hint — but we only store hashes
        # Just show connection instructions with placeholder
        ws_key = keys[0].get("key_prefix", "") + "..."

    return _render_dashboard(user, project, usage, limits, keys, usage_pct,
                             agents_data, mcp_servers_data, signal_volume,
                             signal_types, hourly_volume, ws_key)


@router.post("/dashboard/keys/create")
async def create_key(request: Request):
    """Create a new API key."""
    from hosted.app import get_platform_db
    pdb = get_platform_db()
    user = _require_user(request, pdb)
    if not user:
        return RedirectResponse("/auth/login")

    projects = pdb.get_projects(user["id"])
    if not projects:
        raise HTTPException(400, "No project found")

    form = await request.form()
    name = form.get("key_name", "default")
    plaintext, _ = pdb.create_api_key(projects[0]["id"], name=name)

    # Show the key once
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><title>API Key Created</title>
<style>
body {{ background: #0d1117; color: #e6edf3; font-family: system-ui; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 2rem; max-width: 600px; width: 90%; }}
h2 {{ color: #38bdf8; margin-top: 0; }}
.key {{ background: #0d1117; border: 1px solid #38bdf8; border-radius: 8px; padding: 1rem; font-family: monospace; font-size: 0.9rem; word-break: break-all; margin: 1rem 0; }}
.warn {{ color: #f59e0b; font-size: 0.9rem; }}
a {{ color: #38bdf8; text-decoration: none; }}
</style></head><body>
<div class="card">
<h2>API Key Created</h2>
<p>Copy this key now — it won't be shown again.</p>
<div class="key">{plaintext}</div>
<p class="warn">Store this securely. Use it as: Authorization: Bearer {plaintext[:16]}...</p>
<p><a href="/dashboard">Back to Dashboard</a></p>
</div></body></html>""")


@router.post("/dashboard/keys/{key_id}/revoke")
async def revoke_key(key_id: str, request: Request):
    """Revoke an API key."""
    from hosted.app import get_platform_db
    pdb = get_platform_db()
    user = _require_user(request, pdb)
    if not user:
        return RedirectResponse("/auth/login")
    pdb.revoke_api_key(key_id)
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/dashboard/test-signal")
async def test_signal(request: Request):
    """Send a test signal from the dashboard."""
    from hosted.app import get_platform_db
    from hosted.tenant import get_tenant_state
    pdb = get_platform_db()
    user = _require_user(request, pdb)
    if not user:
        return RedirectResponse("/auth/login")

    projects = pdb.get_projects(user["id"])
    if not projects:
        return RedirectResponse("/dashboard", status_code=302)

    form = await request.form()
    content = form.get("content", "Test signal from dashboard")

    state = get_tenant_state(projects[0]["id"])
    state["bus"].emit(from_agent="dashboard", content=content, signal_type="observation")
    pdb.increment_usage(projects[0]["id"], "signal_count")

    return RedirectResponse("/dashboard", status_code=302)


# ── Login page ───────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing — redirect to dashboard if logged in, otherwise show login."""
    from hosted.app import get_platform_db
    pdb = get_platform_db()
    user = _require_user(request, pdb)
    if user:
        return RedirectResponse("/dashboard")

    return HTMLResponse("""<!DOCTYPE html>
<html><head><title>Vigil Cloud</title>
<style>
body { background: #0d1117; color: #e6edf3; font-family: system-ui; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 3rem; text-align: center; max-width: 400px; }
h1 { color: #38bdf8; margin-bottom: 0.5rem; }
p { color: #8b949e; margin-bottom: 2rem; }
.btn { display: inline-block; background: #238636; color: white; padding: 0.75rem 2rem; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 1rem; }
.btn:hover { background: #2ea043; }
</style></head><body>
<div class="card">
<h1>Vigil Cloud</h1>
<p>Cognitive infrastructure for AI agents.<br>Sign in to manage your Vigil instance.</p>
<a href="/auth/login" class="btn">Sign in with GitHub</a>
</div></body></html>""")


# ── Dashboard HTML renderer ──────────────────────────────────

def _render_dashboard(user, project, usage, limits, keys, usage_pct,
                      agents_data=None, mcp_servers_data=None, signal_volume=None,
                      signal_types=None, hourly_volume=None, ws_key=""):
    """Render the dashboard HTML inline (no template engine needed for MVP)."""
    agents_data = agents_data or []
    mcp_servers_data = mcp_servers_data or []
    signal_volume = signal_volume or []
    signal_types = signal_types or []
    hourly_volume = hourly_volume or []

    # Get the first key prefix for connect instructions
    first_key_prefix = keys[0]['key_prefix'] + "..." if keys else "your-api-key-here"
    has_keys = len(keys) > 0

    # Get recent signals for activity feed
    recent_signals = []
    if project:
        from hosted.tenant import get_tenant_state
        try:
            tenant_state = get_tenant_state(project["id"])
            recent_sigs = tenant_state["bus"].read(hours=24, limit=5)
            recent_signals = [s.to_dict() for s in recent_sigs]
        except Exception:
            pass

    keys_html = ""
    for k in keys:
        keys_html += f"""
        <tr class="table-row">
            <td><code class="inline-code">{k['key_prefix']}...</code></td>
            <td>{k['name']}</td>
            <td class="muted">{k.get('last_used_at') or 'Never'}</td>
            <td>
                <form method="POST" action="/dashboard/keys/{k['id']}/revoke" style="display:inline">
                    <button type="submit" class="btn-sm btn-danger">Revoke</button>
                </form>
            </td>
        </tr>"""

    signal_limit_display = f"{limits['signal_limit']:,}" if limits['signal_limit'] > 0 else "Unlimited"

    # Signal type accent colors for activity feed
    def signal_type_color(stype):
        colors = {
            "observation": "#38bdf8",
            "alert": "#f59e0b",
            "error": "#f87171",
            "action": "#4ade80",
            "warning": "#fb923c",
        }
        return colors.get(stype, "#8b949e")

    activity_html = ""
    if not recent_signals:
        activity_html = "<p class='muted' style='font-size:0.9rem;padding:0.5rem 0;'>No signals yet. Connect an agent or send a test signal above.</p>"
    else:
        for s in recent_signals:
            stype = s.get('signal_type', 'observation')
            accent = signal_type_color(stype)
            activity_html += f"""
        <div class="activity-entry" style="border-left-color:{accent}">
            <div class="activity-meta">
                <span class="activity-agent">{s.get('from_agent','?')}</span>
                <span class="activity-type" style="color:{accent}">{stype}</span>
                <span class="activity-time">{str(s.get('created_at',''))[:19]}</span>
            </div>
            <div class="activity-content">{s.get('content','')[:120]}</div>
        </div>"""

    test_signal_html = "" if not has_keys else """
    <div class="section">
        <div class="section-header">
            <h2 class="section-title">Send Test Signal</h2>
            <div class="section-rule"></div>
        </div>
        <p class="section-desc">Verify your setup — send a test signal and watch it appear in the feed.</p>
        <form method="POST" action="/dashboard/test-signal" class="input-row">
            <input type="text" name="content" placeholder="Test signal content..." value="Hello from Vigil Cloud!"
                   class="text-input">
            <button type="submit" class="btn-primary">Send Signal</button>
        </form>
    </div>"""

    billing_free_html = """
    <div class="billing-cards">
        <div class="billing-card">
            <p class="billing-tier">Pro</p>
            <div class="billing-price"><span class="billing-amount">$9</span><span class="billing-period">/ mo</span></div>
            <ul class="billing-features">
                <li><span class="check">&#10003;</span> Unlimited agents</li>
                <li><span class="check">&#10003;</span> 50K signals / mo</li>
                <li><span class="check">&#10003;</span> Hosted MCP server</li>
                <li><span class="check">&#10003;</span> Dashboard UI</li>
            </ul>
            <form method="POST" action="/billing/checkout/pro">
                <button type="submit" class="billing-btn billing-btn-accent">Upgrade to Pro</button>
            </form>
        </div>
        <div class="billing-card billing-card-popular">
            <div class="billing-popular-badge">Most Popular</div>
            <p class="billing-tier" style="color:#38bdf8">Team</p>
            <div class="billing-price"><span class="billing-amount">$29</span><span class="billing-period">/ mo</span></div>
            <ul class="billing-features">
                <li><span class="check">&#10003;</span> 5 projects</li>
                <li><span class="check">&#10003;</span> 200K signals / mo</li>
                <li><span class="check">&#10003;</span> SSO / team access</li>
                <li><span class="check">&#10003;</span> Priority support</li>
            </ul>
            <form method="POST" action="/billing/checkout/team">
                <button type="submit" class="billing-btn billing-btn-solid">Upgrade to Team</button>
            </form>
        </div>
        <div class="billing-card">
            <p class="billing-tier">Enterprise</p>
            <div class="billing-price"><span class="billing-amount">$99</span><span class="billing-period">/ mo</span></div>
            <ul class="billing-features">
                <li><span class="check">&#10003;</span> Unlimited projects</li>
                <li><span class="check">&#10003;</span> Unlimited signals</li>
                <li><span class="check">&#10003;</span> SLA guarantee</li>
                <li><span class="check">&#10003;</span> Custom frames</li>
            </ul>
            <form method="POST" action="/billing/checkout/enterprise">
                <button type="submit" class="billing-btn billing-btn-ghost">Upgrade to Enterprise</button>
            </form>
        </div>
    </div>"""

    billing_paid_html = """
    <p class="section-desc" style="margin-bottom:1.25rem;">Manage your subscription, update payment method, or cancel anytime.</p>
    <form method="POST" action="/billing/portal">
        <button type="submit" class="btn-primary">Manage Subscription</button>
    </form>"""

    billing_html = billing_free_html if user['tier'] == 'free' else billing_paid_html

    # ── Signal Analytics section ───────────────────────────
    analytics_html = ""
    if signal_types or hourly_volume:
        # Hourly bar chart (24h)
        hourly_chart = ""
        if hourly_volume:
            hour_map = {int(h["hour"]): h["count"] for h in hourly_volume}
            max_hourly = max(hour_map.values()) if hour_map else 1
            bars = ""
            for h in range(24):
                count = hour_map.get(h, 0)
                pct = (count / max_hourly * 100) if max_hourly else 0
                label = f"{h:02d}"
                bars += f'''<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;">
                    <div style="width:100%;background:var(--border);border-radius:3px 3px 0 0;height:80px;position:relative;">
                        <div style="position:absolute;bottom:0;width:100%;height:{pct}%;background:linear-gradient(180deg,#38bdf8,#818cf8);border-radius:3px 3px 0 0;transition:height 0.3s;min-height:{1 if count else 0}px;"></div>
                    </div>
                    <span style="font-size:0.55rem;color:var(--muted);font-family:'JetBrains Mono',monospace;">{label}</span>
                </div>'''

            hourly_chart = f'''
            <div style="margin-bottom:1.5rem;">
                <div style="font-size:0.75rem;font-weight:500;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">Signal Volume (24h by hour)</div>
                <div style="display:flex;gap:2px;align-items:flex-end;">{bars}</div>
            </div>'''

        # Type distribution horizontal bars
        type_chart = ""
        if signal_types:
            type_colors = {
                "observation": "#38bdf8",
                "alert": "#f59e0b",
                "handoff": "#818cf8",
                "summary": "#4ade80",
            }
            total_signals = sum(t["count"] for t in signal_types)
            type_bars = ""
            for t in signal_types:
                color = type_colors.get(t["signal_type"], "#8b949e")
                pct = (t["count"] / total_signals * 100) if total_signals else 0
                type_bars += f'''<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">
                    <span style="width:90px;font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:{color};">{t["signal_type"]}</span>
                    <div style="flex:1;background:var(--border);border-radius:4px;height:20px;overflow:hidden;">
                        <div style="height:100%;width:{pct}%;background:{color};border-radius:4px;opacity:0.8;transition:width 0.3s;"></div>
                    </div>
                    <span style="font-size:0.78rem;color:var(--muted);font-variant-numeric:tabular-nums;width:50px;text-align:right;">{t["count"]}</span>
                </div>'''

            type_chart = f'''
            <div>
                <div style="font-size:0.75rem;font-weight:500;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">Signal Types (7 days)</div>
                {type_bars}
            </div>'''

        analytics_html = f"""
    <div class="section">
        <div class="section-header">
            <h2 class="section-title">Signal Analytics</h2>
            <div class="section-rule"></div>
        </div>
        {hourly_chart}
        {type_chart}
    </div>"""

    # ── Live feed WebSocket script ─────────────────────────
    live_feed_script = ""
    if ws_key:
        live_feed_script = """
<script>
(function() {
  const feed = document.getElementById('live-feed');
  if (!feed) return;

  const typeColors = {
    observation: '#38bdf8', alert: '#f59e0b', error: '#f87171',
    handoff: '#818cf8', summary: '#4ade80', action: '#4ade80',
  };

  function addSignal(s) {
    const color = typeColors[s.signal_type] || '#8b949e';
    const time = (s.created_at || '').slice(0, 19);
    const content = (s.content || '').slice(0, 120);
    const el = document.createElement('div');
    el.className = 'activity-entry';
    el.style.borderLeftColor = color;
    el.style.animation = 'fadeSlide 0.3s ease';
    el.innerHTML = `
      <div class="activity-meta">
        <span class="activity-agent">${s.from_agent || '?'}</span>
        <span class="activity-type" style="color:${color}">${s.signal_type || ''}</span>
        <span class="activity-time">${time}</span>
      </div>
      <div class="activity-content">${content}</div>`;
    feed.prepend(el);
    // Keep max 20
    while (feed.children.length > 20) feed.removeChild(feed.lastChild);
  }

  // Pulse indicator
  const dot = document.getElementById('live-dot');

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(proto + '//' + location.host + '/ws/signals?key=' + encodeURIComponent(feed.dataset.key));
    ws.onopen = () => { if (dot) dot.style.background = '#4ade80'; };
    ws.onclose = () => { if (dot) dot.style.background = '#f87171'; setTimeout(connect, 5000); };
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'ping') return;
        addSignal(data);
      } catch(err) {}
    };
  }
  connect();
})();
</script>
<style>
@keyframes fadeSlide { from { opacity:0; transform:translateY(-8px); } to { opacity:1; transform:translateY(0); } }
</style>"""

    # ── Signal volume sparkline SVG ────────────────────────
    sparkline_svg = ""
    if signal_volume:
        values = [v["count"] for v in signal_volume]
        max_val = max(values) if values else 1
        w, h = 160, 36
        points = []
        for i, v in enumerate(values):
            x = (i / max(len(values) - 1, 1)) * w
            y = h - (v / max_val * h * 0.85) - 2
            points.append(f"{x:.1f},{y:.1f}")
        polyline = " ".join(points)
        # Area fill
        area_points = f"0,{h} " + polyline + f" {w},{h}"
        sparkline_svg = f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="display:block;margin-top:0.5rem;">
          <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#38bdf8" stop-opacity="0.3"/><stop offset="100%" stop-color="#38bdf8" stop-opacity="0.02"/></linearGradient></defs>
          <polygon points="{area_points}" fill="url(#sg)"/>
          <polyline points="{polyline}" fill="none" stroke="#38bdf8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>'''
        total_7d = sum(values)
    else:
        total_7d = 0

    # ── Agents section HTML ────────────────────────────────
    agents_html = ""
    if agents_data:
        agents_rows = ""
        for a in agents_data:
            last = str(a.get("last_seen", ""))[:16]
            agents_rows += f'''<tr class="table-row">
                <td><code class="inline-code">{a["from_agent"]}</code></td>
                <td style="font-variant-numeric:tabular-nums">{a["signal_count"]}</td>
                <td class="muted">{last}</td>
            </tr>'''
        agents_html = f"""
    <div class="section">
        <div class="section-header">
            <h2 class="section-title">Agents</h2>
            <div class="section-rule"></div>
        </div>
        <table>
            <thead><tr><th>Agent</th><th>Signals</th><th>Last Seen</th></tr></thead>
            <tbody>{agents_rows}</tbody>
        </table>
    </div>"""

    # ── MCP Health section HTML ────────────────────────────
    mcp_html = ""
    if mcp_servers_data:
        mcp_cards = ""
        for srv in mcp_servers_data:
            status = srv["status"]
            if status == "healthy":
                badge_bg = "rgba(74,222,128,0.12)"
                badge_color = "#4ade80"
                badge_border = "rgba(74,222,128,0.3)"
            elif status == "degraded":
                badge_bg = "rgba(251,191,36,0.12)"
                badge_color = "#fbbf24"
                badge_border = "rgba(251,191,36,0.3)"
            else:
                badge_bg = "rgba(248,113,113,0.12)"
                badge_color = "#f87171"
                badge_border = "rgba(248,113,113,0.3)"

            mcp_cards += f'''
        <div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:1.25rem;display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;">
            <div>
                <div style="display:flex;align-items:center;gap:0.625rem;margin-bottom:0.35rem;">
                    <code class="inline-code" style="font-size:0.85rem;">{srv["name"]}</code>
                    <span style="background:{badge_bg};color:{badge_color};border:1px solid {badge_border};padding:0.1rem 0.5rem;border-radius:4px;font-size:0.65rem;font-family:'JetBrains Mono',monospace;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">{status}</span>
                </div>
                <div class="muted" style="font-size:0.78rem;">Last seen: {str(srv["last_seen"] or "never")[:16]}</div>
            </div>
            <div style="display:flex;gap:1.5rem;font-size:0.8rem;">
                <div style="text-align:center"><div style="color:var(--accent);font-weight:700;font-size:1.1rem;font-variant-numeric:tabular-nums;">{srv["calls"]:,}</div><div class="muted" style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.06em;">calls</div></div>
                <div style="text-align:center"><div style="color:{"#f87171" if srv["errors"] else "var(--muted)"};font-weight:700;font-size:1.1rem;font-variant-numeric:tabular-nums;">{srv["errors"]}</div><div class="muted" style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.06em;">errors</div></div>
                <div style="text-align:center"><div style="color:var(--bright);font-weight:700;font-size:1.1rem;font-variant-numeric:tabular-nums;">{srv["avg_ms"]}ms</div><div class="muted" style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.06em;">avg</div></div>
            </div>
        </div>'''

        mcp_html = f"""
    <div class="section">
        <div class="section-header">
            <h2 class="section-title">MCP Server Health</h2>
            <div class="section-rule"></div>
        </div>
        <p class="section-desc">Monitored via <code class="inline-code" style="font-size:0.75rem;">mcpwatch</code> — last 24 hours.</p>
        <div style="display:flex;flex-direction:column;gap:0.75rem;">
            {mcp_cards}
        </div>
    </div>"""

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en"><head><title>Dashboard — Vigil Cloud</title>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
<style>
*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

:root {{
  --surface: #050506;
  --panel:   #0d0d0e;
  --card:    #161b22;
  --border:  #21262d;
  --border2: #30363d;
  --accent:  #38bdf8;
  --accent-dim: #0ea5e9;
  --accent-glow: rgba(56,189,248,0.12);
  --muted:   #8b949e;
  --bright:  #e6edf3;
}}

html, body {{
  background: var(--surface);
  color: var(--bright);
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}

/* ── Nav ─────────────────────────────────── */
.nav {{
  background: rgba(13,13,14,0.85);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 0 2rem;
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 50;
}}

.nav-brand {{
  display: flex;
  align-items: center;
  gap: 0.625rem;
  text-decoration: none;
}}

.nav-logo-mark {{
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: rgba(56,189,248,0.08);
  border: 1px solid rgba(56,189,248,0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}}

.nav-brand-name {{
  font-size: 1rem;
  font-weight: 600;
  color: var(--bright);
  letter-spacing: -0.01em;
}}

.tier-badge {{
  display: inline-block;
  background: rgba(56,189,248,0.1);
  color: var(--accent);
  border: 1px solid rgba(56,189,248,0.25);
  padding: 0.1rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

.nav-right {{
  display: flex;
  align-items: center;
  gap: 1rem;
}}

.nav-username {{
  font-size: 0.875rem;
  color: var(--muted);
}}

.nav-avatar {{
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1px solid var(--border2);
}}

.nav-logout {{
  font-size: 0.8rem;
  color: var(--muted);
  text-decoration: none;
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  transition: color 0.15s, border-color 0.15s;
}}

.nav-logout:hover {{
  color: var(--bright);
  border-color: var(--border2);
}}

/* ── Layout ──────────────────────────────── */
.container {{
  max-width: 920px;
  margin: 0 auto;
  padding: 2.5rem 1.25rem 4rem;
}}

/* ── Stats Grid ──────────────────────────── */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}}

.stat-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.5rem;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}}

.stat-card:hover {{
  border-color: rgba(56,189,248,0.3);
  box-shadow: 0 0 20px rgba(56,189,248,0.08);
  transform: translateY(-1px);
}}

.stat-label {{
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 0.625rem;
}}

.stat-value {{
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--accent);
  line-height: 1;
  margin-bottom: 0.75rem;
  font-variant-numeric: tabular-nums;
}}

.bar-bg {{
  background: var(--border2);
  border-radius: 999px;
  height: 6px;
  overflow: hidden;
}}

.bar-fill {{
  height: 6px;
  border-radius: 999px;
  background: linear-gradient(90deg, #38bdf8 0%, #818cf8 100%);
  transition: width 0.4s ease;
  position: relative;
}}

.bar-fill::after {{
  content: '';
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #818cf8;
  box-shadow: 0 0 6px rgba(129,140,248,0.6);
}}

.bar-meta {{
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 0.4rem;
}}

/* ── Section ─────────────────────────────── */
.section {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.75rem;
  margin-bottom: 1.25rem;
}}

.section-header {{
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.25rem;
}}

.section-title {{
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--bright);
  white-space: nowrap;
  letter-spacing: -0.01em;
}}

.section-rule {{
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(56,189,248,0.3) 0%, var(--border) 50%, transparent 100%);
}}

.section-desc {{
  font-size: 0.875rem;
  color: var(--muted);
  margin-bottom: 1rem;
  line-height: 1.5;
}}

/* ── Code Block ──────────────────────────── */
.code-block {{
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  line-height: 1.7;
  white-space: pre;
  overflow-x: auto;
  color: #c9d1d9;
}}

.code-block .hl-cyan   {{ color: #38bdf8; }}
.code-block .hl-green  {{ color: #4ade80; }}
.code-block .hl-muted  {{ color: #8b949e; }}
.code-block .hl-yellow {{ color: #fbbf24; }}

/* ── Inline code ─────────────────────────── */
.inline-code {{
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  color: var(--accent);
}}

/* ── Activity Feed ───────────────────────── */
.activity-entry {{
  border-left: 2px solid;
  padding: 0.75rem 0 0.75rem 1rem;
  margin-bottom: 0.25rem;
}}

.activity-entry + .activity-entry {{
  border-top: 1px solid var(--border);
  padding-top: 0.875rem;
}}

.activity-meta {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}}

.activity-agent {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.775rem;
  font-weight: 500;
  color: var(--accent);
}}

.activity-type {{
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.85;
}}

.activity-time {{
  font-size: 0.7rem;
  color: var(--muted);
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}}

.activity-content {{
  font-size: 0.85rem;
  color: var(--bright);
  opacity: 0.9;
}}

/* ── Table ───────────────────────────────── */
table {{
  width: 100%;
  border-collapse: collapse;
}}

.table-row td, thead th {{
  text-align: left;
  padding: 0.65rem 0.5rem;
  font-size: 0.875rem;
  border-bottom: 1px solid var(--border);
}}

thead th {{
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  padding-bottom: 0.75rem;
}}

.table-row:last-child td {{
  border-bottom: none;
}}

.table-row:hover td {{
  background: rgba(56,189,248,0.03);
}}

.muted {{ color: var(--muted); }}

/* ── Forms / Inputs ──────────────────────── */
.input-row {{
  display: flex;
  gap: 0.625rem;
  align-items: center;
  flex-wrap: wrap;
}}

.text-input {{
  background: var(--panel);
  border: 1px solid var(--border2);
  border-radius: 7px;
  padding: 0.5rem 0.875rem;
  color: var(--bright);
  font-size: 0.875rem;
  font-family: inherit;
  flex: 1;
  min-width: 200px;
  transition: border-color 0.15s, box-shadow 0.15s;
  outline: none;
}}

.text-input:focus {{
  border-color: rgba(56,189,248,0.5);
  box-shadow: 0 0 0 3px rgba(56,189,248,0.08);
}}

.text-input::placeholder {{
  color: var(--muted);
}}

/* ── Buttons ─────────────────────────────── */
.btn-primary {{
  display: inline-block;
  background: var(--accent);
  color: #0d1117;
  padding: 0.5rem 1.125rem;
  border-radius: 7px;
  font-size: 0.875rem;
  font-weight: 600;
  font-family: inherit;
  border: none;
  cursor: pointer;
  text-decoration: none;
  transition: box-shadow 0.2s, background-color 0.2s;
  white-space: nowrap;
}}

.btn-primary:hover {{
  background: #7dd3fc;
  box-shadow: 0 0 18px rgba(56,189,248,0.35);
}}

.btn-sm {{
  padding: 0.25rem 0.6rem;
  font-size: 0.78rem;
  border-radius: 5px;
  border: none;
  cursor: pointer;
  color: white;
  font-family: inherit;
  font-weight: 500;
  transition: opacity 0.15s;
}}

.btn-sm:hover {{ opacity: 0.85; }}

.btn-danger {{
  background: #b91c1c;
}}

.btn-danger:hover {{
  background: #ef4444;
}}

/* ── Billing Cards ───────────────────────── */
.billing-cards {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-top: 0.5rem;
}}

.billing-card {{
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}}

.billing-card:hover {{
  border-color: rgba(56,189,248,0.25);
  box-shadow: 0 0 20px rgba(56,189,248,0.07);
  transform: translateY(-2px);
}}

.billing-card-popular {{
  border-color: rgba(56,189,248,0.45);
  box-shadow: 0 0 0 1px rgba(56,189,248,0.45), 0 0 28px rgba(56,189,248,0.12);
}}

.billing-popular-badge {{
  position: absolute;
  top: -11px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--accent);
  color: #0d1117;
  font-size: 0.65rem;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  padding: 0.2rem 0.75rem;
  border-radius: 999px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}}

.billing-tier {{
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted);
  margin-bottom: 0.5rem;
}}

.billing-price {{
  display: flex;
  align-items: flex-end;
  gap: 0.25rem;
  margin-bottom: 1.125rem;
}}

.billing-amount {{
  font-size: 2rem;
  font-weight: 700;
  color: var(--bright);
  line-height: 1;
}}

.billing-period {{
  font-size: 0.8rem;
  color: var(--muted);
  margin-bottom: 0.2rem;
}}

.billing-features {{
  list-style: none;
  font-size: 0.8rem;
  color: var(--muted);
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  flex: 1;
  margin-bottom: 1.25rem;
}}

.billing-features li {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}

.check {{
  color: var(--accent);
  font-size: 0.7rem;
  flex-shrink: 0;
}}

.billing-btn {{
  width: 100%;
  padding: 0.55rem;
  border-radius: 7px;
  font-size: 0.8rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  border: none;
  transition: opacity 0.15s, box-shadow 0.2s, background-color 0.2s;
}}

.billing-btn:hover {{ opacity: 0.9; }}

.billing-btn-accent {{
  background: transparent;
  color: var(--accent);
  border: 1px solid rgba(56,189,248,0.4) !important;
  border: 1px solid rgba(56,189,248,0.4);
  transition: background 0.2s, border-color 0.2s;
}}

.billing-btn-accent:hover {{
  background: rgba(56,189,248,0.08);
  border-color: rgba(56,189,248,0.6) !important;
  opacity: 1;
}}

.billing-btn-solid {{
  background: var(--accent);
  color: #0d1117;
}}

.billing-btn-solid:hover {{
  background: #7dd3fc;
  box-shadow: 0 0 16px rgba(56,189,248,0.3);
  opacity: 1;
}}

.billing-btn-ghost {{
  background: transparent;
  color: var(--muted);
  border: 1px solid var(--border2) !important;
  border: 1px solid var(--border2);
  transition: color 0.2s, border-color 0.2s;
}}

.billing-btn-ghost:hover {{
  color: var(--bright);
  border-color: var(--border2) !important;
  opacity: 1;
}}

/* ── Responsive ──────────────────────────── */
@media (max-width: 600px) {{
  .nav {{ padding: 0 1rem; }}
  .nav-username {{ display: none; }}
  .container {{ padding: 1.5rem 1rem 3rem; }}
  .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .section {{ padding: 1.25rem; }}
  .billing-cards {{ grid-template-columns: 1fr; }}
  .input-row {{ flex-direction: column; align-items: stretch; }}
  .text-input {{ min-width: unset; }}
}}
</style>
</head>
<body>

<nav class="nav">
  <div class="nav-brand">
    <div class="nav-logo-mark">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="2.5" fill="#38bdf8"/>
        <circle cx="7" cy="7" r="5.5" stroke="#38bdf8" stroke-width="1" stroke-dasharray="2 2" opacity="0.5"/>
      </svg>
    </div>
    <span class="nav-brand-name">vigil</span>
    <span class="tier-badge">{user['tier']}</span>
  </div>
  <div class="nav-right">
    <span class="nav-username">{user['name']}</span>
    <img class="nav-avatar" src="{user.get('avatar_url', '')}" alt="{user['name']}" />
    <a href="/auth/logout" class="nav-logout">Logout</a>
  </div>
</nav>

<div class="container">

  <!-- Stats Grid -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Signals this month</div>
      <div class="stat-value">{usage['signal_count']:,}</div>
      <div class="bar-bg"><div class="bar-fill" style="width:{usage_pct}%"></div></div>
      <div class="bar-meta">{usage_pct}% of {signal_limit_display}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Compiles</div>
      <div class="stat-value">{usage['compile_count']:,}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Tier</div>
      <div class="stat-value" style="font-size:1.4rem">{user['tier'].title()}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">7-Day Volume</div>
      <div class="stat-value">{total_7d:,}</div>
      {sparkline_svg}
    </div>
  </div>

  <!-- Connect Your Agent -->
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">Connect Your Agent</h2>
      <div class="section-rule"></div>
    </div>
    <p class="section-desc">{"Create an API key below, then add this to your agent:" if not has_keys else "Add this to your agent's environment or MCP config:"}</p>
    <div class="code-block"><span class="hl-muted"># Environment</span>
<span class="hl-cyan">VIGIL_API_URL</span>=https://app.vigil-agent.com
<span class="hl-cyan">VIGIL_API_KEY</span>={first_key_prefix}

<span class="hl-muted"># Send a signal:</span>
<span class="hl-green">curl</span> -X POST https://app.vigil-agent.com/api/signal \
  -H <span class="hl-yellow">"Authorization: Bearer {first_key_prefix}"</span> \
  -H <span class="hl-yellow">"Content-Type: application/json"</span> \
  -d '<span class="hl-yellow">{{"agent":"my-agent","content":"hello world","signal_type":"observation"}}</span>'

<span class="hl-muted"># Boot with awareness:</span>
<span class="hl-green">curl</span> -H <span class="hl-yellow">"Authorization: Bearer {first_key_prefix}"</span> \
  https://app.vigil-agent.com/api/boot</div>
  </div>

  {test_signal_html}

  <!-- Signal Analytics -->
  {analytics_html}

  <!-- Recent Activity (live via WebSocket) -->
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">Recent Activity</h2>
      <div class="section-rule"></div>
      <div style="display:flex;align-items:center;gap:0.4rem;margin-left:auto;">
        <div id="live-dot" style="width:6px;height:6px;border-radius:50%;background:#8b949e;"></div>
        <span style="font-size:0.65rem;color:var(--muted);font-family:'JetBrains Mono',monospace;">LIVE</span>
      </div>
    </div>
    <div id="live-feed" data-key="{first_key_prefix}">
    {activity_html}
    </div>
  </div>

  {agents_html}

  {mcp_html}

  <!-- API Keys -->
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">API Keys</h2>
      <div class="section-rule"></div>
    </div>
    <table>
      <thead>
        <tr><th>Key</th><th>Name</th><th>Last Used</th><th></th></tr>
      </thead>
      <tbody>{keys_html if keys_html else '<tr><td colspan="4" style="padding:1rem 0.5rem;color:var(--muted);font-size:0.875rem;">No API keys yet. Create one below.</td></tr>'}</tbody>
    </table>
    <div style="margin-top:1.25rem">
      <form method="POST" action="/dashboard/keys/create" class="input-row">
        <input type="text" name="key_name" placeholder="Key name" value="default" class="text-input" style="max-width:220px;flex:unset;">
        <button type="submit" class="btn-primary">Create Key</button>
      </form>
    </div>
  </div>

  <!-- Billing -->
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">Billing</h2>
      <div class="section-rule"></div>
    </div>
    {billing_html}
  </div>

</div>
{live_feed_script}
</body></html>""")
