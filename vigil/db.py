"""
Vigil Database Layer — SQLite storage with zero infrastructure.
"""

import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

SCHEMA = """
-- Signals: lightweight event protocol for agent communication
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent TEXT NOT NULL,
    to_agent TEXT,
    signal_type TEXT NOT NULL DEFAULT 'observation',
    content TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at DATETIME
);

-- Awareness: compiled system state
CREATE TABLE IF NOT EXISTS awareness (
    id INTEGER PRIMARY KEY DEFAULT 1,
    summary TEXT DEFAULT '',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT DEFAULT 'system'
);

-- Brain state: daemon-compiled hot context
CREATE TABLE IF NOT EXISTS brain_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    current_frame TEXT DEFAULT 'default',
    hot_context TEXT DEFAULT '{}',
    compiled_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Frames: context modes with trigger keywords
CREATE TABLE IF NOT EXISTS frames (
    id TEXT PRIMARY KEY,
    description TEXT,
    triggers TEXT DEFAULT '[]',
    active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Focus: priority queue for active work
CREATE TABLE IF NOT EXISTS focus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    priority INTEGER DEFAULT 5,
    description TEXT NOT NULL,
    owner TEXT,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Sessions: agent session tracking
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    frame TEXT,
    summary TEXT,
    next_steps TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_unacked ON signals(acknowledged) WHERE acknowledged = 0;
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_focus_status ON focus(status);
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id);
"""


class VigilDB:
    """SQLite database for Vigil state management."""

    def __init__(self, path: str = "vigil.db"):
        self.path = Path(path)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            # Ensure singleton rows exist
            conn.execute(
                "INSERT OR IGNORE INTO awareness (id, summary) VALUES (1, '')"
            )
            conn.execute(
                "INSERT OR IGNORE INTO brain_state (id, current_frame, hot_context) VALUES (1, 'default', '{}')"
            )

    @contextmanager
    def connect(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        """Execute query, return single row as dict."""
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def query_all(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute query, return all rows as dicts."""
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Execute statement, return lastrowid."""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid

    # -- Signal operations --

    def create_signal(
        self,
        from_agent: str,
        content: str,
        signal_type: str = "observation",
        to_agent: Optional[str] = None,
    ) -> int:
        """Record a signal."""
        return self.execute(
            "INSERT INTO signals (from_agent, to_agent, signal_type, content) VALUES (?, ?, ?, ?)",
            (from_agent, to_agent, signal_type, content),
        )

    def get_unacknowledged_signals(self, limit: int = 10) -> List[Dict]:
        """Get unacknowledged signals, newest first."""
        return self.query_all(
            "SELECT id, from_agent, to_agent, signal_type, content, created_at "
            "FROM signals WHERE acknowledged = 0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    def get_recent_signals(self, hours: int = 1, limit: int = 10) -> List[Dict]:
        """Get recent signals within a time window."""
        return self.query_all(
            "SELECT id, from_agent, to_agent, signal_type, content, created_at "
            "FROM signals WHERE created_at > datetime('now', ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (f"-{hours} hours", limit),
        )

    def acknowledge_signal(self, signal_id: int):
        """Mark a signal as acknowledged."""
        self.execute(
            "UPDATE signals SET acknowledged = 1, acknowledged_at = CURRENT_TIMESTAMP WHERE id = ?",
            (signal_id,),
        )

    # -- Awareness operations --

    def get_awareness(self) -> Optional[Dict]:
        """Get current awareness summary."""
        return self.query_one("SELECT summary, updated_at, updated_by FROM awareness WHERE id = 1")

    def update_awareness(self, summary: str, updated_by: str = "daemon"):
        """Update awareness summary."""
        self.execute(
            "UPDATE awareness SET summary = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = 1",
            (summary[:2000], updated_by),
        )

    # -- Brain state operations --

    def get_brain_state(self) -> Optional[Dict]:
        """Get daemon-compiled hot context."""
        row = self.query_one("SELECT current_frame, hot_context, compiled_at FROM brain_state WHERE id = 1")
        if row and row.get("hot_context"):
            try:
                row["hot_context"] = json.loads(row["hot_context"])
            except (json.JSONDecodeError, TypeError):
                row["hot_context"] = {}
        return row

    def update_brain_state(self, frame: str, context: dict):
        """Update daemon-compiled hot context."""
        self.execute(
            "UPDATE brain_state SET current_frame = ?, hot_context = ?, compiled_at = CURRENT_TIMESTAMP WHERE id = 1",
            (frame, json.dumps(context, separators=(",", ":"))),
        )

    # -- Frame operations --

    def register_frame(self, frame_id: str, description: str = "", triggers: list = None):
        """Register or update a frame."""
        triggers_json = json.dumps(triggers or [])
        self.execute(
            "INSERT OR REPLACE INTO frames (id, description, triggers) VALUES (?, ?, ?)",
            (frame_id, description, triggers_json),
        )

    def get_frames(self) -> List[Dict]:
        """Get all active frames."""
        rows = self.query_all("SELECT id, description, triggers FROM frames WHERE active = 1")
        for row in rows:
            try:
                row["triggers"] = json.loads(row.get("triggers", "[]"))
            except (json.JSONDecodeError, TypeError):
                row["triggers"] = []
        return rows

    # -- Focus operations --

    def add_focus(self, description: str, priority: int = 5, owner: Optional[str] = None) -> int:
        """Add a focus item."""
        return self.execute(
            "INSERT INTO focus (priority, description, owner) VALUES (?, ?, ?)",
            (priority, description, owner),
        )

    def get_active_focus(self, limit: int = 5) -> List[Dict]:
        """Get active focus items sorted by priority."""
        return self.query_all(
            "SELECT id, priority, description, owner, status FROM focus "
            "WHERE status NOT IN ('completed', 'done') ORDER BY priority LIMIT ?",
            (limit,),
        )

    def complete_focus(self, focus_id: int):
        """Mark a focus item as completed."""
        self.execute("UPDATE focus SET status = 'completed' WHERE id = ?", (focus_id,))

    # -- Session operations --

    def start_session(self, agent_id: str, frame: Optional[str] = None) -> int:
        """Start a new agent session."""
        return self.execute(
            "INSERT INTO sessions (agent_id, frame) VALUES (?, ?)",
            (agent_id, frame),
        )

    def end_session(self, session_id: int, summary: str = "", next_steps: str = ""):
        """End an agent session."""
        self.execute(
            "UPDATE sessions SET summary = ?, next_steps = ?, ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (summary, next_steps, session_id),
        )

    # -- Maintenance --

    def compress_old_signals(self, days_old: int = 7) -> int:
        """Delete old acknowledged signals. Returns count deleted."""
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM signals WHERE acknowledged = 1 AND created_at < datetime('now', ?)",
                (f"-{days_old} days",),
            )
            return cursor.rowcount
