"""Hosted tier configuration."""

import os

DATA_DIR = os.environ.get("VIGIL_DATA_DIR", "/data/vigil")
PLATFORM_DB = os.path.join(DATA_DIR, "platform.db")
TENANTS_DIR = os.path.join(DATA_DIR, "tenants")

SESSION_SECRET = os.environ.get("VIGIL_SESSION_SECRET", "change-me-in-production")

GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

APP_URL = os.environ.get("VIGIL_APP_URL", "https://app.vigil-agent.com")

TIERS = {
    "free": {
        "signal_limit": 5_000,
        "agent_limit": 2,
        "project_limit": 1,
        "price_monthly": 0,
    },
    "pro": {
        "signal_limit": 50_000,
        "agent_limit": 0,  # unlimited
        "project_limit": 1,
        "price_monthly": 900,  # $9 in cents
    },
    "team": {
        "signal_limit": 200_000,
        "agent_limit": 0,
        "project_limit": 5,
        "price_monthly": 2900,
    },
    "enterprise": {
        "signal_limit": 0,  # unlimited
        "agent_limit": 0,
        "project_limit": 0,
        "price_monthly": 9900,
    },
}


def get_tier_limits(tier: str) -> dict:
    """Get limits for a tier. Returns enterprise limits for unknown tiers."""
    return TIERS.get(tier, TIERS["enterprise"])
