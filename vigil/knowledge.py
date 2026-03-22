"""
Vigil Knowledge Base — Persistent facts that accumulate over time.

Signals are ephemeral. Knowledge persists. Agents use knowledge to store
learned patterns, decisions, and facts that should survive compaction.

Usage:
    from vigil.knowledge import KnowledgeBase
    kb = KnowledgeBase(db)
    kb.set("deploy_branch", "main", category="config", source_agent="devops")
    entry = kb.get("deploy_branch")
    results = kb.recall("deploy")  # fuzzy search
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

from vigil.db import VigilDB


# Schema extension — called by VigilDB._init_db via KNOWLEDGE_SCHEMA
KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    source_agent TEXT,
    confidence REAL DEFAULT 1.0,
    metadata TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_key ON knowledge(key);
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_agent ON knowledge(source_agent);
"""


@dataclass
class KnowledgeEntry:
    """A single knowledge entry."""
    id: int
    key: str
    value: str
    category: str = "general"
    source_agent: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "source_agent": self.source_agent,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class KnowledgeBase:
    """Persistent knowledge store for AI agents."""

    def __init__(self, db: VigilDB):
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self):
        """Create knowledge table if it doesn't exist."""
        with self.db.connect() as conn:
            conn.executescript(KNOWLEDGE_SCHEMA)

    def set(
        self,
        key: str,
        value: str,
        category: str = "general",
        source_agent: Optional[str] = None,
        confidence: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> KnowledgeEntry:
        """Store or update a knowledge entry. Upserts by key."""
        meta_json = json.dumps(metadata or {}, separators=(",", ":"))
        self.db.execute(
            "INSERT INTO knowledge (key, value, category, source_agent, confidence, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "value = excluded.value, category = excluded.category, "
            "source_agent = excluded.source_agent, confidence = excluded.confidence, "
            "metadata = excluded.metadata, updated_at = CURRENT_TIMESTAMP",
            (key, value, category, source_agent, confidence, meta_json),
        )
        return self.get(key)

    def get(self, key: str) -> Optional[KnowledgeEntry]:
        """Get a knowledge entry by exact key."""
        row = self.db.query_one(
            "SELECT * FROM knowledge WHERE key = ?", (key,)
        )
        return self._row_to_entry(row) if row else None

    def delete(self, key: str) -> bool:
        """Delete a knowledge entry by key. Returns True if deleted."""
        existing = self.get(key)
        if not existing:
            return False
        self.db.execute("DELETE FROM knowledge WHERE key = ?", (key,))
        return True

    def recall(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[KnowledgeEntry]:
        """Fuzzy-match knowledge entries by key or value content.

        Searches both key and value fields using LIKE matching.
        Results are ordered by relevance (key match > value match).
        """
        terms = query.strip().split()
        if not terms:
            return []

        # Build WHERE clause: all terms must match in key OR value
        conditions = []
        params = []
        for term in terms:
            pattern = f"%{term}%"
            conditions.append("(key LIKE ? OR value LIKE ? OR category LIKE ?)")
            params.extend([pattern, pattern, pattern])

        where = " AND ".join(conditions)
        if category:
            where += " AND category = ?"
            params.append(category)

        # Order: key matches first (more specific), then by recency
        rows = self.db.query_all(
            f"SELECT *, "
            f"CASE WHEN key LIKE ? THEN 1 ELSE 0 END as key_match "
            f"FROM knowledge WHERE {where} "
            f"ORDER BY key_match DESC, updated_at DESC LIMIT ?",
            tuple([f"%{query}%"] + params + [limit]),
        )
        return [self._row_to_entry(r) for r in rows]

    def list(
        self,
        category: Optional[str] = None,
        source_agent: Optional[str] = None,
        limit: int = 50,
    ) -> List[KnowledgeEntry]:
        """List knowledge entries with optional filtering."""
        conditions = []
        params = []

        if category:
            conditions.append("category = ?")
            params.append(category)
        if source_agent:
            conditions.append("source_agent = ?")
            params.append(source_agent)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.db.query_all(
            f"SELECT * FROM knowledge {where} ORDER BY updated_at DESC LIMIT ?",
            tuple(params + [limit]),
        )
        return [self._row_to_entry(r) for r in rows]

    def categories(self) -> List[str]:
        """Get all distinct knowledge categories."""
        rows = self.db.query_all(
            "SELECT DISTINCT category FROM knowledge ORDER BY category"
        )
        return [r["category"] for r in rows]

    def count(self, category: Optional[str] = None) -> int:
        """Count knowledge entries, optionally filtered by category."""
        if category:
            row = self.db.query_one(
                "SELECT COUNT(*) as cnt FROM knowledge WHERE category = ?",
                (category,),
            )
        else:
            row = self.db.query_one("SELECT COUNT(*) as cnt FROM knowledge")
        return row["cnt"] if row else 0

    def _row_to_entry(self, row: dict) -> KnowledgeEntry:
        """Convert a database row to a KnowledgeEntry."""
        metadata = {}
        if row.get("metadata"):
            try:
                metadata = json.loads(row["metadata"])
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        return KnowledgeEntry(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            category=row.get("category", "general"),
            source_agent=row.get("source_agent"),
            confidence=row.get("confidence", 1.0),
            metadata=metadata,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
