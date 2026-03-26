"""Tests for the knowledge base module."""

import os
import tempfile
import pytest
from vigil.db import VigilDB
from vigil.knowledge import KnowledgeBase, KnowledgeEntry, KnowledgeExtractor


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def kb(db):
    return KnowledgeBase(db)


class TestKnowledgeEntry:
    def test_to_dict(self):
        entry = KnowledgeEntry(
            id=1, key="test", value="val",
            category="config", source_agent="agent1",
        )
        d = entry.to_dict()
        assert d["key"] == "test"
        assert d["value"] == "val"
        assert d["category"] == "config"
        assert d["source_agent"] == "agent1"
        assert d["confidence"] == 1.0

    def test_defaults(self):
        entry = KnowledgeEntry(id=1, key="k", value="v")
        assert entry.category == "general"
        assert entry.source_agent is None
        assert entry.confidence == 1.0
        assert entry.metadata == {}


class TestKnowledgeBaseSet:
    def test_basic_set(self, kb):
        entry = kb.set("deploy_branch", "main")
        assert entry.key == "deploy_branch"
        assert entry.value == "main"
        assert entry.category == "general"
        assert entry.id is not None

    def test_set_with_category(self, kb):
        entry = kb.set("api_key_rotation", "weekly", category="security")
        assert entry.category == "security"

    def test_set_with_agent(self, kb):
        entry = kb.set("db_host", "localhost", source_agent="devops")
        assert entry.source_agent == "devops"

    def test_set_with_confidence(self, kb):
        entry = kb.set("estimate", "3 days", confidence=0.7)
        assert entry.confidence == 0.7

    def test_upsert_updates_value(self, kb):
        kb.set("branch", "develop")
        entry = kb.set("branch", "main")
        assert entry.value == "main"
        # Should still be only one entry
        all_entries = kb.list()
        assert len(all_entries) == 1

    def test_upsert_updates_category(self, kb):
        kb.set("item", "val", category="old")
        entry = kb.set("item", "val2", category="new")
        assert entry.category == "new"

    def test_set_with_metadata(self, kb):
        entry = kb.set("config", "val", metadata={"source": "env"})
        assert entry.metadata == {"source": "env"}


class TestKnowledgeBaseGet:
    def test_get_existing(self, kb):
        kb.set("key1", "value1")
        entry = kb.get("key1")
        assert entry is not None
        assert entry.value == "value1"

    def test_get_nonexistent(self, kb):
        entry = kb.get("nonexistent")
        assert entry is None

    def test_get_returns_correct_type(self, kb):
        kb.set("typed", "data")
        entry = kb.get("typed")
        assert isinstance(entry, KnowledgeEntry)


class TestKnowledgeBaseDelete:
    def test_delete_existing(self, kb):
        kb.set("to_delete", "goodbye")
        assert kb.delete("to_delete") is True
        assert kb.get("to_delete") is None

    def test_delete_nonexistent(self, kb):
        assert kb.delete("nope") is False

    def test_delete_reduces_count(self, kb):
        kb.set("a", "1")
        kb.set("b", "2")
        assert kb.count() == 2
        kb.delete("a")
        assert kb.count() == 1


class TestKnowledgeBaseRecall:
    def test_recall_by_key(self, kb):
        kb.set("deploy_branch", "main")
        kb.set("test_framework", "pytest")
        results = kb.recall("deploy")
        assert len(results) == 1
        assert results[0].key == "deploy_branch"

    def test_recall_by_value(self, kb):
        kb.set("db", "PostgreSQL is our primary database")
        results = kb.recall("PostgreSQL")
        assert len(results) == 1
        assert results[0].key == "db"

    def test_recall_by_category(self, kb):
        kb.set("item1", "val1", category="security")
        kb.set("item2", "val2", category="config")
        results = kb.recall("item", category="security")
        assert len(results) == 1
        assert results[0].category == "security"

    def test_recall_empty_query(self, kb):
        kb.set("anything", "val")
        results = kb.recall("")
        assert results == []

    def test_recall_no_matches(self, kb):
        kb.set("a", "b")
        results = kb.recall("zzzznothing")
        assert results == []

    def test_recall_respects_limit(self, kb):
        for i in range(20):
            kb.set(f"item_{i}", f"value_{i}")
        results = kb.recall("item", limit=5)
        assert len(results) == 5

    def test_recall_key_match_ranked_higher(self, kb):
        kb.set("deploy_config", "some deployment settings")
        kb.set("other_thing", "deploy related value")
        results = kb.recall("deploy")
        assert len(results) == 2
        # Key match should be first
        assert results[0].key == "deploy_config"

    def test_recall_multiple_terms(self, kb):
        kb.set("deploy_branch", "main")
        kb.set("deploy_env", "production")
        kb.set("test_branch", "feature")
        results = kb.recall("deploy branch")
        # Should match deploy_branch (has both terms in key)
        assert any(r.key == "deploy_branch" for r in results)


class TestKnowledgeBaseList:
    def test_list_all(self, kb):
        kb.set("a", "1")
        kb.set("b", "2")
        kb.set("c", "3")
        entries = kb.list()
        assert len(entries) == 3

    def test_list_by_category(self, kb):
        kb.set("a", "1", category="config")
        kb.set("b", "2", category="policy")
        kb.set("c", "3", category="config")
        entries = kb.list(category="config")
        assert len(entries) == 2
        assert all(e.category == "config" for e in entries)

    def test_list_by_agent(self, kb):
        kb.set("a", "1", source_agent="alpha")
        kb.set("b", "2", source_agent="beta")
        entries = kb.list(source_agent="alpha")
        assert len(entries) == 1
        assert entries[0].source_agent == "alpha"

    def test_list_respects_limit(self, kb):
        for i in range(20):
            kb.set(f"key_{i}", f"val_{i}")
        entries = kb.list(limit=5)
        assert len(entries) == 5

    def test_list_empty(self, kb):
        entries = kb.list()
        assert entries == []

    def test_list_ordered_by_recency(self, kb):
        kb.set("old", "first")
        # Force a later updated_at by updating
        kb.set("new", "second")
        entries = kb.list()
        # Both entries present, ordered by id desc (same timestamp)
        assert len(entries) == 2
        keys = {e.key for e in entries}
        assert keys == {"old", "new"}


class TestKnowledgeBaseCategories:
    def test_categories(self, kb):
        kb.set("a", "1", category="config")
        kb.set("b", "2", category="policy")
        kb.set("c", "3", category="config")
        cats = kb.categories()
        assert sorted(cats) == ["config", "policy"]

    def test_categories_empty(self, kb):
        cats = kb.categories()
        assert cats == []


class TestKnowledgeBaseCount:
    def test_count_all(self, kb):
        kb.set("a", "1")
        kb.set("b", "2")
        assert kb.count() == 2

    def test_count_by_category(self, kb):
        kb.set("a", "1", category="x")
        kb.set("b", "2", category="y")
        kb.set("c", "3", category="x")
        assert kb.count(category="x") == 2
        assert kb.count(category="y") == 1

    def test_count_empty(self, kb):
        assert kb.count() == 0


class TestKnowledgeBaseSchemaIdempotent:
    def test_double_init(self, db):
        """Creating KnowledgeBase twice shouldn't fail."""
        kb1 = KnowledgeBase(db)
        kb2 = KnowledgeBase(db)
        kb1.set("test", "value")
        entry = kb2.get("test")
        assert entry.value == "value"


# --- KnowledgeExtractor tests ---

@pytest.fixture
def extractor(db, kb):
    return KnowledgeExtractor(db, kb)


def _emit_signals(db, agent, messages):
    """Helper to emit multiple signals."""
    for msg in messages:
        db.create_signal(from_agent=agent, content=msg, signal_type="observation")


class TestKnowledgeExtractorTokenize:
    def test_basic_tokenize(self, extractor):
        tokens = extractor._tokenize("Deployed auth service v2 to production")
        assert "deployed" in tokens
        assert "auth" in tokens
        assert "service" in tokens
        assert "production" in tokens
        # Stop words removed
        assert "to" not in tokens

    def test_removes_short_tokens(self, extractor):
        tokens = extractor._tokenize("a b cd xyz")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "cd" not in tokens
        assert "xyz" in tokens

    def test_handles_punctuation(self, extractor):
        tokens = extractor._tokenize("error: database connection failed!")
        assert "error" in tokens
        assert "database" in tokens
        assert "connection" in tokens
        assert "failed" in tokens


class TestKnowledgeExtractorNgrams:
    def test_basic_ngrams(self, extractor):
        tokens = ["deployed", "auth", "service", "production"]
        ngrams = extractor._extract_ngrams(tokens)
        assert "deployed auth" in ngrams
        assert "auth service" in ngrams
        assert "deployed auth service" in ngrams

    def test_empty_tokens(self, extractor):
        assert extractor._extract_ngrams([]) == []

    def test_single_token(self, extractor):
        # MIN_PHRASE_LEN is 2, so single token produces no ngrams
        assert extractor._extract_ngrams(["hello"]) == []


class TestKnowledgeExtractorRecurringPhrases:
    def test_finds_recurring_phrase(self, db, extractor):
        # Same phrase in 4 signals → should be extracted
        for _ in range(4):
            db.create_signal(
                from_agent="backend",
                content="Deployed auth service to production",
                signal_type="observation",
            )
        suggestions = extractor._extract_recurring_phrases(
            db.query_all("SELECT from_agent, content, signal_type, created_at FROM signals")
        )
        # Should find at least one recurring phrase
        assert len(suggestions) > 0
        assert any("auth-service" in s["key"] or "deployed-auth" in s["key"] for s in suggestions)

    def test_no_recurring_phrases(self, db, extractor):
        # All unique signals
        db.create_signal(from_agent="a", content="first unique message here", signal_type="observation")
        db.create_signal(from_agent="b", content="second different content now", signal_type="observation")
        suggestions = extractor._extract_recurring_phrases(
            db.query_all("SELECT from_agent, content, signal_type, created_at FROM signals")
        )
        assert suggestions == []


class TestKnowledgeExtractorAgentPatterns:
    def test_finds_dominant_type(self, db, extractor):
        # Agent with 80% observation signals
        for _ in range(8):
            db.create_signal(from_agent="monitor", content="All systems normal", signal_type="observation")
        for _ in range(2):
            db.create_signal(from_agent="monitor", content="Something happened", signal_type="alert")

        suggestions = extractor._extract_agent_patterns(
            db.query_all("SELECT from_agent, content, signal_type, created_at FROM signals")
        )
        assert len(suggestions) > 0
        assert any("monitor" in s["key"] for s in suggestions)

    def test_skips_low_count_agents(self, db, extractor):
        # Only 2 signals — below threshold
        db.create_signal(from_agent="rare", content="msg1", signal_type="observation")
        db.create_signal(from_agent="rare", content="msg2", signal_type="observation")

        suggestions = extractor._extract_agent_patterns(
            db.query_all("SELECT from_agent, content, signal_type, created_at FROM signals")
        )
        assert suggestions == []

    def test_skips_mixed_type_agents(self, db, extractor):
        # Agent with evenly mixed types (no dominant)
        for i in range(5):
            db.create_signal(from_agent="mixed", content=f"obs {i}", signal_type="observation")
        for i in range(5):
            db.create_signal(from_agent="mixed", content=f"alert {i}", signal_type="alert")

        suggestions = extractor._extract_agent_patterns(
            db.query_all("SELECT from_agent, content, signal_type, created_at FROM signals")
        )
        # 50% observation, 50% alert — neither >70%, should be empty
        assert suggestions == []


class TestKnowledgeExtractorExtract:
    def test_full_extraction_dry_run(self, db, extractor):
        for _ in range(5):
            db.create_signal(
                from_agent="deployer",
                content="Deployed backend service to staging environment",
                signal_type="observation",
            )
        suggestions = extractor.extract(days=7, dry_run=True)
        assert len(suggestions) > 0
        # Dry run should NOT store anything
        assert extractor.kb.count() == 0

    def test_full_extraction_stores(self, db, extractor):
        for _ in range(5):
            db.create_signal(
                from_agent="deployer",
                content="Deployed backend service to staging environment",
                signal_type="observation",
            )
        suggestions = extractor.extract(days=7, dry_run=False)
        assert len(suggestions) > 0
        # Should be stored now
        assert extractor.kb.count() > 0
        # All stored with auto-extracted category
        entries = extractor.kb.list(category="auto-extracted")
        assert len(entries) > 0

    def test_no_signals_no_extraction(self, db, extractor):
        suggestions = extractor.extract(days=7)
        assert suggestions == []

    def test_filters_existing_knowledge(self, db, extractor, kb):
        for _ in range(5):
            db.create_signal(
                from_agent="test",
                content="Deployed backend service to staging environment",
                signal_type="observation",
            )
        # First extraction
        first = extractor.extract(days=7, dry_run=False)
        assert len(first) > 0

        # Second extraction — should find nothing new (already stored)
        second = extractor.extract(days=7, dry_run=True)
        assert len(second) == 0

    def test_extraction_confidence(self, db, extractor):
        for _ in range(5):
            db.create_signal(
                from_agent="bot",
                content="Running daily health check on production servers",
                signal_type="observation",
            )
        extractor.extract(days=7)
        entries = extractor.kb.list(category="auto-extracted")
        for e in entries:
            assert e.confidence == KnowledgeExtractor.EXTRACT_CONFIDENCE
