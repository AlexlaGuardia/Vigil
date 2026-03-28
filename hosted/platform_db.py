"""Platform database — accounts, projects, API keys, usage."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from hosted.keys import generate_api_key, hash_key
from hosted.config import PLATFORM_DB

PLATFORM_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    github_id INTEGER UNIQUE,
    email TEXT,
    name TEXT,
    avatar_url TEXT,
    tier TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    name TEXT DEFAULT 'default',
    last_used_at DATETIME,
    revoked INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    month TEXT NOT NULL,
    signal_count INTEGER DEFAULT 0,
    compile_count INTEGER DEFAULT 0,
    UNIQUE(project_id, month)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix) WHERE revoked = 0;
CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_account ON projects(account_id);
CREATE INDEX IF NOT EXISTS idx_usage_project_month ON usage(project_id, month);
"""


class PlatformDB:
    """Platform-level database for multi-tenant management."""

    def __init__(self, db_path: str = None):
        self.path = Path(db_path or PLATFORM_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self.connect() as conn:
            conn.executescript(PLATFORM_SCHEMA)

    # ── Accounts ─────────────────────────────────────────────

    def create_account(
        self,
        github_id: int,
        email: str,
        name: str,
        avatar_url: str = "",
    ) -> dict:
        """Create or update an account from GitHub OAuth."""
        account_id = str(uuid.uuid4())
        with self.connect() as conn:
            # Upsert — if github_id exists, update info
            existing = conn.execute(
                "SELECT id FROM accounts WHERE github_id = ?", (github_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE accounts SET email = ?, name = ?, avatar_url = ? WHERE github_id = ?",
                    (email, name, avatar_url, github_id),
                )
                return dict(conn.execute(
                    "SELECT * FROM accounts WHERE github_id = ?", (github_id,)
                ).fetchone())
            conn.execute(
                "INSERT INTO accounts (id, github_id, email, name, avatar_url) VALUES (?, ?, ?, ?, ?)",
                (account_id, github_id, email, name, avatar_url),
            )
            return dict(conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone())

    def get_account(self, account_id: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            return dict(row) if row else None

    def get_account_by_github(self, github_id: int) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE github_id = ?", (github_id,)).fetchone()
            return dict(row) if row else None

    def update_tier(self, account_id: str, tier: str, stripe_customer_id: str = None):
        with self.connect() as conn:
            if stripe_customer_id:
                conn.execute(
                    "UPDATE accounts SET tier = ?, stripe_customer_id = ? WHERE id = ?",
                    (tier, stripe_customer_id, account_id),
                )
            else:
                conn.execute("UPDATE accounts SET tier = ? WHERE id = ?", (tier, account_id))

    # ── Projects ─────────────────────────────────────────────

    def create_project(self, account_id: str, name: str) -> dict:
        """Create a new project for an account."""
        project_id = str(uuid.uuid4())
        slug = name.lower().replace(" ", "-")[:50]
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, account_id, name, slug) VALUES (?, ?, ?, ?)",
                (project_id, account_id, name, slug),
            )
            return {"id": project_id, "account_id": account_id, "name": name, "slug": slug}

    def get_projects(self, account_id: str) -> list:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM projects WHERE account_id = ? ORDER BY created_at", (account_id,)
            ).fetchall()]

    def get_project(self, project_id: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return dict(row) if row else None

    def count_projects(self, account_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM projects WHERE account_id = ?", (account_id,)
            ).fetchone()
            return row["cnt"]

    # ── API Keys ─────────────────────────────────────────────

    def create_api_key(self, project_id: str, name: str = "default") -> tuple[str, dict]:
        """Create an API key. Returns (plaintext_key, key_record)."""
        key_id = str(uuid.uuid4())
        plaintext, key_hash, prefix = generate_api_key()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO api_keys (id, project_id, key_hash, key_prefix, name) VALUES (?, ?, ?, ?, ?)",
                (key_id, project_id, key_hash, prefix, name),
            )
            return plaintext, {"id": key_id, "project_id": project_id, "prefix": prefix, "name": name}

    def resolve_api_key(self, key: str) -> Optional[dict]:
        """Resolve an API key to its project + account. Returns None if invalid/revoked."""
        prefix = key[:12]
        key_hash_check = hash_key(key)
        with self.connect() as conn:
            candidates = conn.execute(
                "SELECT ak.id, ak.project_id, ak.key_hash, p.account_id, a.tier "
                "FROM api_keys ak "
                "JOIN projects p ON ak.project_id = p.id "
                "JOIN accounts a ON p.account_id = a.id "
                "WHERE ak.key_prefix = ? AND ak.revoked = 0",
                (prefix,),
            ).fetchall()
            for row in candidates:
                if row["key_hash"] == key_hash_check:
                    # Update last_used
                    conn.execute(
                        "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (row["id"],),
                    )
                    return dict(row)
        return None

    def revoke_api_key(self, key_id: str):
        with self.connect() as conn:
            conn.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (key_id,))

    def get_api_keys(self, project_id: str) -> list:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT id, key_prefix, name, last_used_at, created_at FROM api_keys "
                "WHERE project_id = ? AND revoked = 0 ORDER BY created_at",
                (project_id,),
            ).fetchall()]

    # ── Usage ────────────────────────────────────────────────

    def increment_usage(self, project_id: str, field: str = "signal_count"):
        """Increment a usage counter for the current month."""
        month = datetime.utcnow().strftime("%Y-%m")
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO usage (project_id, month, {field}) VALUES (?, ?, 1) "
                f"ON CONFLICT(project_id, month) DO UPDATE SET {field} = {field} + 1",
                (project_id, month),
            )

    def get_usage(self, project_id: str, month: str = None) -> dict:
        """Get usage for a project in a given month."""
        month = month or datetime.utcnow().strftime("%Y-%m")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT signal_count, compile_count FROM usage WHERE project_id = ? AND month = ?",
                (project_id, month),
            ).fetchone()
            if row:
                return dict(row)
            return {"signal_count": 0, "compile_count": 0}
