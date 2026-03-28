"""Tenant isolation — per-tenant Vigil state with LRU caching."""

import os
from functools import lru_cache
from pathlib import Path

from vigil.api import build_state
from hosted.config import TENANTS_DIR


def get_tenant_db_path(project_id: str) -> str:
    """Get the database path for a tenant project."""
    return os.path.join(TENANTS_DIR, project_id, "vigil.db")


def ensure_tenant_dir(project_id: str) -> str:
    """Ensure the tenant directory exists. Returns the db path."""
    db_path = get_tenant_db_path(project_id)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return db_path


@lru_cache(maxsize=64)
def get_tenant_state(project_id: str) -> dict:
    """Get or create the Vigil state dict for a tenant.

    LRU-cached so each tenant's DB connection is reused across requests.
    Max 64 tenants in memory (~320MB worst case at 5MB per connection).
    """
    db_path = ensure_tenant_dir(project_id)
    return build_state(db_path)


def evict_tenant(project_id: str):
    """Remove a tenant from the cache (e.g. after deletion)."""
    get_tenant_state.cache_clear()
