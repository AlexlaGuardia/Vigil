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

    return _render_dashboard(user, project, usage, limits, keys, usage_pct)


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

def _render_dashboard(user, project, usage, limits, keys, usage_pct):
    """Render the dashboard HTML inline (no template engine needed for MVP)."""
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
        <tr>
            <td><code>{k['key_prefix']}...</code></td>
            <td>{k['name']}</td>
            <td>{k.get('last_used_at') or 'Never'}</td>
            <td>
                <form method="POST" action="/dashboard/keys/{k['id']}/revoke" style="display:inline">
                    <button type="submit" class="btn-sm btn-danger">Revoke</button>
                </form>
            </td>
        </tr>"""

    signal_limit_display = f"{limits['signal_limit']:,}" if limits['signal_limit'] > 0 else "Unlimited"

    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><title>Dashboard — Vigil Cloud</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0d1117; color: #e6edf3; font-family: system-ui; }}
.nav {{ background: #161b22; border-bottom: 1px solid #30363d; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }}
.nav h1 {{ font-size: 1.2rem; color: #38bdf8; }}
.nav-right {{ display: flex; align-items: center; gap: 1rem; }}
.nav-right img {{ width: 32px; height: 32px; border-radius: 50%; }}
.nav-right a {{ color: #8b949e; text-decoration: none; font-size: 0.9rem; }}
.container {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; }}
.stat-card .label {{ color: #8b949e; font-size: 0.85rem; margin-bottom: 0.25rem; }}
.stat-card .value {{ font-size: 1.5rem; font-weight: 700; color: #38bdf8; }}
.section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.section h2 {{ font-size: 1.1rem; margin-bottom: 1rem; color: #e6edf3; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 0.5rem; border-bottom: 1px solid #30363d; font-size: 0.9rem; }}
th {{ color: #8b949e; }}
code {{ background: #0d1117; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.85rem; }}
.bar-bg {{ background: #30363d; border-radius: 4px; height: 8px; margin-top: 0.5rem; }}
.bar-fill {{ background: #38bdf8; height: 8px; border-radius: 4px; transition: width 0.3s; }}
.btn {{ display: inline-block; background: #238636; color: white; padding: 0.5rem 1rem; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 0.9rem; border: none; cursor: pointer; }}
.btn:hover {{ background: #2ea043; }}
.btn-sm {{ padding: 0.25rem 0.5rem; font-size: 0.8rem; border-radius: 4px; border: none; cursor: pointer; color: white; }}
.btn-danger {{ background: #da3633; }}
.btn-danger:hover {{ background: #f85149; }}
.connect {{ background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; font-family: monospace; font-size: 0.85rem; white-space: pre; overflow-x: auto; }}
.tier-badge {{ display: inline-block; background: #30363d; color: #38bdf8; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; }}
</style></head><body>
<div class="nav">
    <h1>vigil <span class="tier-badge">{user['tier']}</span></h1>
    <div class="nav-right">
        <span>{user['name']}</span>
        <img src="{user.get('avatar_url', '')}" alt="">
        <a href="/auth/logout">Logout</a>
    </div>
</div>
<div class="container">
    <div class="grid">
        <div class="stat-card">
            <div class="label">Signals this month</div>
            <div class="value">{usage['signal_count']:,}</div>
            <div class="bar-bg"><div class="bar-fill" style="width: {usage_pct}%"></div></div>
            <div class="label" style="margin-top:0.25rem">{usage_pct}% of {signal_limit_display}</div>
        </div>
        <div class="stat-card">
            <div class="label">Compiles</div>
            <div class="value">{usage['compile_count']:,}</div>
        </div>
        <div class="stat-card">
            <div class="label">Tier</div>
            <div class="value">{user['tier'].title()}</div>
        </div>
        <div class="stat-card">
            <div class="label">Project</div>
            <div class="value">{project['name'] if project else 'None'}</div>
        </div>
    </div>

    <div class="section">
        <h2>Connect Your Agent</h2>
        <p style="color:#8b949e; margin-bottom:1rem; font-size:0.9rem">{"Create an API key below, then add this to your agent:" if not has_keys else "Add this to your agent's environment or MCP config:"}</p>
        <div class="connect">VIGIL_API_URL=https://app.vigil-agent.com
VIGIL_API_KEY={first_key_prefix}

# Send a signal:
curl -X POST https://app.vigil-agent.com/api/signal \\
  -H "Authorization: Bearer {first_key_prefix}" \\
  -H "Content-Type: application/json" \\
  -d '{{"agent":"my-agent","content":"hello world","signal_type":"observation"}}'

# Boot with awareness:
curl -H "Authorization: Bearer {first_key_prefix}" \\
  https://app.vigil-agent.com/api/boot</div>
    </div>

    {"" if not has_keys else '''<div class="section">
        <h2>Send Test Signal</h2>
        <p style="color:#8b949e; margin-bottom:0.75rem; font-size:0.9rem">Verify your setup — send a test signal right now.</p>
        <form method="POST" action="/dashboard/test-signal" style="display:flex; gap:0.5rem; align-items:center;">
            <input type="text" name="content" placeholder="Test signal content..." value="Hello from Vigil Cloud!"
                   style="background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:0.5rem; color:#e6edf3; font-size:0.9rem; flex:1;">
            <button type="submit" class="btn">Send Signal</button>
        </form>
    </div>'''}

    <div class="section">
        <h2>Recent Activity</h2>
        {"<p style='color:#8b949e; font-size:0.9rem'>No signals yet. Connect an agent or send a test signal above.</p>" if not recent_signals else ""}
        {"".join(f"""<div style="border-bottom:1px solid #21262d; padding:0.5rem 0;">
            <span style="color:#38bdf8; font-size:0.8rem; font-family:monospace;">{s.get('from_agent','?')}</span>
            <span style="color:#8b949e; font-size:0.75rem; margin-left:0.5rem;">{s.get('signal_type','')}</span>
            <span style="color:#8b949e; font-size:0.75rem; float:right;">{str(s.get('created_at',''))[:19]}</span>
            <div style="color:#e6edf3; font-size:0.85rem; margin-top:0.25rem;">{s.get('content','')[:120]}</div>
        </div>""" for s in recent_signals)}
    </div>

    <div class="section">
        <h2>API Keys</h2>
        <table>
            <thead><tr><th>Key</th><th>Name</th><th>Last Used</th><th></th></tr></thead>
            <tbody>{keys_html if keys_html else '<tr><td colspan="4" style="color:#8b949e">No API keys yet</td></tr>'}</tbody>
        </table>
        <form method="POST" action="/dashboard/keys/create" style="margin-top:1rem; display:flex; gap:0.5rem; align-items:center;">
            <input type="text" name="key_name" placeholder="Key name" value="default"
                   style="background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:0.5rem; color:#e6edf3; font-size:0.9rem;">
            <button type="submit" class="btn">Create Key</button>
        </form>
    </div>

    <div class="section">
        <h2>Billing</h2>
        {"" if user['tier'] != 'free' else '''
        <p style="color:#8b949e; margin-bottom:1rem; font-size:0.9rem">Upgrade for more signals, unlimited agents, and hosted dashboard.</p>
        <div style="display:flex; gap:0.75rem; flex-wrap:wrap;">
            <form method="POST" action="/billing/checkout/pro"><button type="submit" class="btn">Upgrade to Pro — $9/mo</button></form>
            <form method="POST" action="/billing/checkout/team"><button type="submit" class="btn" style="background:#6f42c1;">Upgrade to Team — $29/mo</button></form>
            <form method="POST" action="/billing/checkout/enterprise"><button type="submit" class="btn" style="background:#0969da;">Upgrade to Enterprise — $99/mo</button></form>
        </div>
        '''}
        {"" if user['tier'] == 'free' else '''
        <p style="color:#8b949e; margin-bottom:1rem; font-size:0.9rem">Manage your subscription, update payment method, or cancel.</p>
        <form method="POST" action="/billing/portal"><button type="submit" class="btn">Manage Subscription</button></form>
        '''}
    </div>
</div>
</body></html>""")
