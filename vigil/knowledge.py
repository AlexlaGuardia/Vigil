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


# --- Auto-extraction ---

# Common English stop words + short tokens to ignore
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could must need dare ought "
    "i me my we us our you your he him his she her it its they them their "
    "this that these those what which who whom how when where why "
    "and or but nor not no so if then else for from by at to in on of "
    "with as into about between through during before after above below "
    "up down out off over under again further once here there all each "
    "every both few more most other some such only own same than too very "
    "just also now still already yet even much many well back also got "
    "get set run new old let use try one two make way".split()
)


class KnowledgeExtractor:
    """Analyzes signal patterns and suggests knowledge entries.

    Runs during the daemon's maintenance cycle. Looks for:
    1. Recurring phrases in signals (3+ occurrences)
    2. Agent activity patterns (consistent behaviors)
    3. Key terms that appear across multiple agents

    Stores suggestions with confidence=0.5 and category='auto-extracted'.
    Never overwrites existing knowledge entries.
    """

    MIN_OCCURRENCES = 3  # Phrase must appear this many times
    MIN_PHRASE_LEN = 2   # Minimum words in a phrase
    MAX_PHRASE_LEN = 4   # Maximum words in a phrase
    EXTRACT_CONFIDENCE = 0.5

    def __init__(self, db: "VigilDB", kb: Optional["KnowledgeBase"] = None):
        self.db = db
        self.kb = kb or KnowledgeBase(db)

    def extract(self, days: int = 7, dry_run: bool = False) -> List[Dict[str, Any]]:
        """Analyze recent signals and extract knowledge suggestions.

        Args:
            days: How many days of signals to analyze
            dry_run: If True, return suggestions without storing them

        Returns:
            List of extracted knowledge entries (dicts with key, value, reason)
        """
        # Get recent signals
        signals = self.db.query_all(
            "SELECT from_agent, content, signal_type, created_at "
            "FROM signals WHERE created_at > datetime('now', ?)"
            " ORDER BY created_at DESC",
            (f"-{days} days",),
        )

        if len(signals) < self.MIN_OCCURRENCES:
            return []

        suggestions = []

        # Strategy 1: Recurring phrases across signals
        suggestions.extend(self._extract_recurring_phrases(signals))

        # Strategy 2: Agent activity patterns
        suggestions.extend(self._extract_agent_patterns(signals))

        # Filter out existing knowledge
        suggestions = self._filter_existing(suggestions)

        # Store if not dry run
        if not dry_run:
            for s in suggestions:
                self.kb.set(
                    key=s["key"],
                    value=s["value"],
                    category="auto-extracted",
                    source_agent="vigil-daemon",
                    confidence=self.EXTRACT_CONFIDENCE,
                    metadata={"reason": s["reason"], "occurrences": s.get("occurrences", 0)},
                )

        return suggestions

    def _tokenize(self, text: str) -> List[str]:
        """Split text into lowercase tokens, removing punctuation and stop words."""
        # Remove common punctuation, keep alphanumeric and hyphens
        cleaned = ""
        for ch in text.lower():
            if ch.isalnum() or ch in " -_":
                cleaned += ch
            else:
                cleaned += " "
        tokens = [t for t in cleaned.split() if t and t not in _STOP_WORDS and len(t) > 2]
        return tokens

    def _extract_ngrams(self, tokens: List[str]) -> List[str]:
        """Extract n-grams from a token list."""
        ngrams = []
        for n in range(self.MIN_PHRASE_LEN, self.MAX_PHRASE_LEN + 1):
            for i in range(len(tokens) - n + 1):
                ngram = " ".join(tokens[i:i + n])
                ngrams.append(ngram)
        return ngrams

    def _extract_recurring_phrases(self, signals: List[Dict]) -> List[Dict]:
        """Find phrases that recur across multiple signals."""
        from collections import Counter

        phrase_counts: Counter = Counter()
        phrase_agents: Dict[str, set] = {}

        for sig in signals:
            tokens = self._tokenize(sig["content"])
            ngrams = self._extract_ngrams(tokens)
            # Dedupe within a single signal
            seen = set()
            for ng in ngrams:
                if ng not in seen:
                    phrase_counts[ng] += 1
                    if ng not in phrase_agents:
                        phrase_agents[ng] = set()
                    phrase_agents[ng].add(sig["from_agent"])
                    seen.add(ng)

        suggestions = []
        for phrase, count in phrase_counts.most_common(20):
            if count < self.MIN_OCCURRENCES:
                break
            agents = phrase_agents.get(phrase, set())
            agent_str = ", ".join(sorted(agents))

            suggestions.append({
                "key": f"pattern:{phrase.replace(' ', '-')}",
                "value": f"Recurring pattern: '{phrase}' appeared {count} times in signals from {agent_str}",
                "reason": f"Appeared in {count} signals across {len(agents)} agent(s)",
                "occurrences": count,
            })

        return suggestions[:10]  # Cap at 10 per cycle

    def _extract_agent_patterns(self, signals: List[Dict]) -> List[Dict]:
        """Identify consistent agent behaviors."""
        from collections import Counter, defaultdict

        agent_types: Dict[str, Counter] = defaultdict(Counter)
        agent_counts: Counter = Counter()

        for sig in signals:
            agent = sig["from_agent"]
            agent_counts[agent] += 1
            agent_types[agent][sig["signal_type"]] += 1

        suggestions = []
        for agent, count in agent_counts.most_common(10):
            if count < 5:
                continue
            # Find dominant signal type
            type_counts = agent_types[agent]
            dominant_type = type_counts.most_common(1)[0]
            dominant_pct = dominant_type[1] / count * 100

            if dominant_pct > 70:
                suggestions.append({
                    "key": f"agent-pattern:{agent}",
                    "value": (
                        f"Agent '{agent}' has emitted {count} signals, "
                        f"{dominant_pct:.0f}% are {dominant_type[0]} type"
                    ),
                    "reason": f"Consistent {dominant_type[0]} behavior from {agent} ({count} signals)",
                    "occurrences": count,
                })

        return suggestions[:5]  # Cap at 5 per cycle

    def _filter_existing(self, suggestions: List[Dict]) -> List[Dict]:
        """Remove suggestions that duplicate existing knowledge."""
        filtered = []
        for s in suggestions:
            existing = self.kb.get(s["key"])
            if not existing:
                filtered.append(s)
        return filtered
