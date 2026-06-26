"""Hosted tier configuration."""

import os
import secrets

ENV = os.environ.get("VIGIL_ENV", "development").lower()

DATA_DIR = os.environ.get("VIGIL_DATA_DIR", "/data/vigil")
PLATFORM_DB = os.path.join(DATA_DIR, "platform.db")
TENANTS_DIR = os.path.join(DATA_DIR, "tenants")

# Session cookies are signed with this. A shared, guessable default (the old
# "change-me-in-production") lets anyone forge a session for a known account_id,
# so refuse to start in production without a real secret. In dev/test, mint a
# random per-process secret rather than a known literal — sessions just don't
# survive a restart, which is fine locally.
SESSION_SECRET = os.environ.get("VIGIL_SESSION_SECRET")
if not SESSION_SECRET:
    if ENV in ("production", "prod"):
        raise RuntimeError(
            "VIGIL_SESSION_SECRET must be set when VIGIL_ENV=production "
            "(refusing to sign sessions with a default secret)."
        )
    SESSION_SECRET = secrets.token_urlsafe(32)

GITHUB_CLIENT_ID = os.environ.get("VIGIL_GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("VIGIL_GITHUB_CLIENT_SECRET", "")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

STRIPE_PRICES = {
    "pro": os.environ.get("VIGIL_STRIPE_PRICE_PRO", ""),
    "team": os.environ.get("VIGIL_STRIPE_PRICE_TEAM", ""),
    "enterprise": os.environ.get("VIGIL_STRIPE_PRICE_ENTERPRISE", ""),
}

APP_URL = os.environ.get("VIGIL_APP_URL", "https://app.vigil-agent.com")

TIERS = {
    "free": {
        "signal_limit": 5_000,
        "agent_limit": 2,
        "project_limit": 1,
        "price_monthly": 0,
        "rate_limit_per_min": 10,
    },
    "pro": {
        "signal_limit": 50_000,
        "agent_limit": 0,  # unlimited
        "project_limit": 1,
        "price_monthly": 900,  # $9 in cents
        "rate_limit_per_min": 60,
    },
    "team": {
        "signal_limit": 200_000,
        "agent_limit": 0,
        "project_limit": 5,
        "price_monthly": 2900,
        "rate_limit_per_min": 300,
    },
    "enterprise": {
        "signal_limit": 0,  # unlimited
        "agent_limit": 0,
        "project_limit": 0,
        "price_monthly": 9900,
        "rate_limit_per_min": 0,  # unlimited
    },
}


def get_tier_limits(tier: str) -> dict:
    """Get limits for a tier. Returns enterprise limits for unknown tiers."""
    return TIERS.get(tier, TIERS["enterprise"])
