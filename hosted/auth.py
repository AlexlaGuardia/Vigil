"""GitHub OAuth authentication for Vigil hosted tier."""

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import Request, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from hosted.config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_SECRET, APP_URL
from hosted.platform_db import PlatformDB

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

SESSION_COOKIE = "vigil_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

_serializer = URLSafeTimedSerializer(SESSION_SECRET)


def get_login_url(state: str = None) -> str:
    """Build GitHub OAuth authorize URL."""
    state = state or secrets.token_urlsafe(16)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{APP_URL}/auth/callback",
        "scope": "read:user user:email",
        "state": state,
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}", state


async def exchange_code(code: str) -> dict:
    """Exchange OAuth code for access token, then fetch user info."""
    async with httpx.AsyncClient() as client:
        # Exchange code for token
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        token_data = resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(400, f"OAuth failed: {token_data.get('error_description', 'unknown error')}")

        # Fetch user info
        resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        user = resp.json()

        # Fetch email if not public
        email = user.get("email")
        if not email:
            resp = await client.get(
                f"{GITHUB_USER_URL}/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            emails = resp.json()
            if isinstance(emails, list):
                primary = next((e for e in emails if e.get("primary")), None)
                email = primary["email"] if primary else (emails[0]["email"] if emails else "")

        return {
            "github_id": user["id"],
            "name": user.get("name") or user.get("login", ""),
            "email": email or "",
            "avatar_url": user.get("avatar_url", ""),
            "login": user.get("login", ""),
        }


def create_session_cookie(account_id: str) -> str:
    """Create a signed session cookie value."""
    return _serializer.dumps(account_id)


def read_session_cookie(cookie_value: str) -> str | None:
    """Read and verify a session cookie. Returns account_id or None."""
    try:
        return _serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


async def get_current_user(request: Request, pdb: PlatformDB) -> dict | None:
    """FastAPI dependency — get current authenticated user from session cookie."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    account_id = read_session_cookie(cookie)
    if not account_id:
        return None
    return pdb.get_account(account_id)
