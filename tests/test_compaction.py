"""Tests for signal compaction engine."""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from vigil.db import VigilDB
from vigil.compaction import SignalCompactor, COMPACTION_SCHEMA, SUMMARY_BUDGET


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def compactor(db):
    return SignalCompactor(db)


def _insert_signal(db, from_agent, content, days_ago, signal_type="observation"):
    """Insert a signal with a backdated created_at."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO signals (from_agent, signal_type, content, created_at) VALUES (?, ?, ?, ?)",
            (from_agent, signal_type, content, ts),
        )


def _insert_summary(db, period, agent_id, summary, signal_count, days_ago_start, days_ago_end):
    """Insert a compacted summary with backdated date ranges."""
    start = (datetime.now(timezone.utc) - timedelta(days=days_ago_start)).strftime("%Y-%m-%d %H:%M:%S")
    end = (datetime.now(timezone.utc) - timedelta(days=days_ago_end)).strftime("%Y-%m-%d %H:%M:%S")
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO compacted_summaries
            (period, agent_id, summary, signal_count, date_range_start, date_range_end)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (period, agent_id, summary, signal_count, start, end),
        )


class TestCompactionSchema:
    def test_table_created(self, compactor, db):
        with db.connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='compacted_summaries'"
            ).fetchone()
        assert tables is not None

    def test_schema_string_defined(self):
        assert "compacted_summaries" in COMPACTION_SCHEMA
        assert "period" in COMPACTION_SCHEMA
        assert "signal_count" in COMPACTION_SCHEMA


class TestDailyCompaction:
    def test_compacts_old_signals(self, compactor, db):
        _insert_signal(db, "agent1", "did thing A", 2)
        _insert_signal(db, "agent1", "did thing B", 2)

        stats = compactor.compact()
        assert stats["daily_summaries"] == 1
        assert stats["signals_compacted"] == 2

        with db.connect() as conn:
            remaining = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()
        assert dict(remaining)["c"] == 0

    def test_preserves_recent_signals(self, compactor, db):
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO signals (from_agent, signal_type, content) VALUES (?, ?, ?)",
                ("agent1", "observation", "very recent"),
            )

        stats = compactor.compact()
        assert stats["daily_summaries"] == 0
        assert stats["signals_compacted"] == 0

        with db.connect() as conn:
            remaining = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()
        assert dict(remaining)["c"] == 1

    def test_groups_by_agent_and_day(self, compactor, db):
        _insert_signal(db, "agent1", "agent1 work", 2)
        _insert_signal(db, "agent2", "agent2 work", 2)

        stats = compactor.compact()
        assert stats["daily_summaries"] == 2

    def test_dry_run_no_changes(self, compactor, db):
        _insert_signal(db, "agent1", "will survive", 3)

        stats = compactor.compact(dry_run=True)
        assert stats["daily_summaries"] == 1
        assert stats["dry_run"] is True

        with db.connect() as conn:
            remaining = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()
        assert dict(remaining)["c"] == 1

    def test_idempotent(self, compactor, db):
        _insert_signal(db, "agent1", "some work", 3)

        compactor.compact()
        stats2 = compactor.compact()
        assert stats2["daily_summaries"] == 0

    def test_summary_truncation(self, compactor, db):
        for i in range(20):
            _insert_signal(db, "agent1", f"Long signal content number {i}. " * 5, 2)

        compactor.compact()

        history = compactor.get_history(days=30, agent="agent1")
        assert len(history) == 1
        assert len(history[0]["summary"]) <= SUMMARY_BUDGET

    def test_multiple_days(self, compactor, db):
        _insert_signal(db, "agent1", "day 2 work", 2)
        _insert_signal(db, "agent1", "day 3 work", 3)
        _insert_signal(db, "agent1", "day 5 work", 5)

        stats = compactor.compact()
        assert stats["daily_summaries"] == 3


class TestWeeklyCompaction:
    def test_merges_daily_into_weekly(self, compactor, db):
        # Use same days_ago to guarantee both land in the same ISO week
        _insert_summary(db, "daily", "agent1", "Monday work", 5, 10, 10)
        _insert_summary(db, "daily", "agent1", "Tuesday work", 3, 10, 10)

        stats = compactor.compact()
        assert stats["weekly_digests"] == 1

        with db.connect() as conn:
            dailies = conn.execute(
                "SELECT COUNT(*) as c FROM compacted_summaries WHERE period = 'daily'"
            ).fetchone()
        assert dict(dailies)["c"] == 0

    def test_preserves_recent_dailies(self, compactor, db):
        _insert_summary(db, "daily", "agent1", "Recent daily", 5, 3, 3)

        stats = compactor.compact()
        assert stats["weekly_digests"] == 0

    def test_groups_by_agent(self, compactor, db):
        _insert_summary(db, "daily", "agent1", "A work", 5, 10, 10)
        _insert_summary(db, "daily", "agent2", "B work", 3, 10, 10)

        stats = compactor.compact()
        assert stats["weekly_digests"] == 2

    def test_weekly_idempotent(self, compactor, db):
        _insert_summary(db, "daily", "agent1", "Old daily", 5, 10, 10)

        compactor.compact()
        stats2 = compactor.compact()
        assert stats2["weekly_digests"] == 0


class TestMonthlyCompaction:
    def test_merges_weekly_into_monthly(self, compactor, db):
        _insert_summary(db, "weekly", "agent1", "Week 1 digest", 20, 40, 35)
        _insert_summary(db, "weekly", "agent1", "Week 2 digest", 15, 45, 40)

        stats = compactor.compact()
        assert stats["monthly_snapshots"] >= 1

    def test_preserves_recent_weeklies(self, compactor, db):
        _insert_summary(db, "weekly", "agent1", "Recent weekly", 10, 12, 10)

        stats = compactor.compact()
        assert stats["monthly_snapshots"] == 0

    def test_monthly_idempotent(self, compactor, db):
        _insert_summary(db, "weekly", "agent1", "Old weekly", 20, 40, 35)

        compactor.compact()
        stats2 = compactor.compact()
        assert stats2["monthly_snapshots"] == 0


class TestGetHistory:
    def test_returns_summaries_in_range(self, compactor, db):
        _insert_summary(db, "daily", "agent1", "Day 1", 5, 3, 3)
        _insert_summary(db, "daily", "agent1", "Day 2", 3, 2, 2)

        history = compactor.get_history(days=7)
        assert len(history) == 2

    def test_filters_by_agent(self, compactor, db):
        _insert_summary(db, "daily", "agent1", "A work", 5, 3, 3)
        _insert_summary(db, "daily", "agent2", "B work", 3, 3, 3)

        history = compactor.get_history(days=7, agent="agent1")
        assert len(history) == 1
        assert history[0]["agent_id"] == "agent1"

    def test_ordered_newest_first(self, compactor, db):
        _insert_summary(db, "daily", "agent1", "Older", 5, 5, 5)
        _insert_summary(db, "daily", "agent1", "Newer", 3, 2, 2)

        history = compactor.get_history(days=10)
        assert history[0]["summary"] == "Newer"

    def test_respects_days_limit(self, compactor, db):
        _insert_summary(db, "daily", "agent1", "Recent", 5, 3, 3)
        _insert_summary(db, "monthly", "agent1", "Old snapshot", 100, 90, 60)

        history = compactor.get_history(days=30)
        assert len(history) == 1

    def test_empty_history(self, compactor, db):
        history = compactor.get_history()
        assert history == []


class TestFullLifecycle:
    def test_signals_flow_through_all_tiers(self, compactor, db):
        """Signals → daily → weekly → monthly."""
        # 3 days old — becomes daily summaries
        _insert_signal(db, "cc", "deployed v1.2", 3)
        _insert_signal(db, "cc", "fixed login bug", 3)

        # 10 days old dailies — becomes weekly
        _insert_summary(db, "daily", "cc", "Mon: shipped features", 4, 12, 12)
        _insert_summary(db, "daily", "cc", "Tue: bugfixes", 3, 11, 11)

        # 35 days old weekly — becomes monthly
        _insert_summary(db, "weekly", "cc", "Week 8 digest", 20, 38, 35)

        stats = compactor.compact()
        assert stats["daily_summaries"] == 1
        assert stats["weekly_digests"] == 1
        assert stats["monthly_snapshots"] == 1
        assert stats["signals_compacted"] == 2

    def test_summary_content_preserved(self, compactor, db):
        """Verify summary text contains source signal content."""
        _insert_signal(db, "cc", "shipped auth feature", 2)
        _insert_signal(db, "cc", "fixed caching bug", 2)

        compactor.compact()

        history = compactor.get_history(days=7, agent="cc")
        assert len(history) == 1
        assert "shipped auth feature" in history[0]["summary"]
        assert "fixed caching bug" in history[0]["summary"]
