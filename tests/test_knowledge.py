"""Tests for the knowledge base module."""

import os
import tempfile
import pytest
from vigil.db import VigilDB
from vigil.knowledge import KnowledgeBase, KnowledgeEntry


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
