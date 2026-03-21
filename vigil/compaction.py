"""
Vigil Signal Compaction — Tiered retention with summary synthesis.

Compresses old signals into progressively coarser summaries,
keeping context fresh without losing history.

Tiers:
  <24h:  keep raw signals (untouched)
  1-7d:  group by agent + day → daily summaries
  7-30d: merge daily summaries → weekly digests
  30d+:  merge weekly digests → monthly snapshots
"""

from typing import Dict, List, Optional

from vigil.signals import _truncate_at_sentence

COMPACTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS compacted_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    signal_count INTEGER NOT NULL DEFAULT 0,
    date_range_start DATETIME NOT NULL,
    date_range_end DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_compacted_period ON compacted_summaries(period);
CREATE INDEX IF NOT EXISTS idx_compacted_agent ON compacted_summaries(agent_id);
CREATE INDEX IF NOT EXISTS idx_compacted_date_range ON compacted_summaries(date_range_start, date_range_end);
"""

SUMMARY_BUDGET = 800


class SignalCompactor:
    """Compacts old signals into tiered summaries."""

    def __init__(self, db):
        """
        Args:
            db: VigilDB instance (compacted_summaries table created by VigilDB schema)
        """
        self.db = db

    def compact(self, dry_run: bool = False) -> Dict:
        """
        Run full compaction cycle across all tiers.

        Args:
            dry_run: If True, calculate stats without modifying data.

        Returns:
            Stats dict with counts per tier.
        """
        stats = {
            "daily_summaries": 0,
            "weekly_digests": 0,
            "monthly_snapshots": 0,
            "signals_compacted": 0,
            "dry_run": dry_run,
        }

        daily = self._compact_daily(dry_run)
        stats["daily_summaries"] = daily["summaries_created"]
        stats["signals_compacted"] += daily["signals_removed"]

        weekly = self._compact_weekly(dry_run)
        stats["weekly_digests"] = weekly["digests_created"]

        monthly = self._compact_monthly(dry_run)
        stats["monthly_snapshots"] = monthly["snapshots_created"]

        return stats

    def _compact_daily(self, dry_run: bool) -> Dict:
        """Compact raw signals from 1-7 days ago into daily summaries."""
        result = {"summaries_created": 0, "signals_removed": 0}

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT from_agent, date(created_at) as day,
                       GROUP_CONCAT(content, ' | ') as combined,
                       COUNT(*) as cnt,
                       MIN(created_at) as range_start,
                       MAX(created_at) as range_end
                FROM signals
                WHERE created_at < datetime('now', '-1 day')
                  AND created_at >= datetime('now', '-7 days')
                GROUP BY from_agent, date(created_at)
                """
            ).fetchall()

            for row in rows:
                row = dict(row)
                existing = conn.execute(
                    """
                    SELECT id FROM compacted_summaries
                    WHERE period = 'daily' AND agent_id = ?
                      AND date(date_range_start) = ?
                    """,
                    (row["from_agent"], row["day"]),
                ).fetchone()

                if existing:
                    continue

                summary = _truncate_at_sentence(row["combined"], SUMMARY_BUDGET)

                if not dry_run:
                    conn.execute(
                        """
                        INSERT INTO compacted_summaries
                        (period, agent_id, summary, signal_count, date_range_start, date_range_end)
                        VALUES ('daily', ?, ?, ?, ?, ?)
                        """,
                        (row["from_agent"], summary, row["cnt"],
                         row["range_start"], row["range_end"]),
                    )
                    conn.execute(
                        """
                        DELETE FROM signals
                        WHERE from_agent = ? AND date(created_at) = ?
                          AND created_at < datetime('now', '-1 day')
                        """,
                        (row["from_agent"], row["day"]),
                    )
                    result["signals_removed"] += row["cnt"]

                result["summaries_created"] += 1

        return result

    def _compact_weekly(self, dry_run: bool) -> Dict:
        """Merge daily summaries older than 7 days into weekly digests."""
        result = {"digests_created": 0}

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_id,
                       strftime('%Y-%W', date_range_start) as week,
                       GROUP_CONCAT(summary, ' | ') as combined,
                       SUM(signal_count) as total_count,
                       MIN(date_range_start) as range_start,
                       MAX(date_range_end) as range_end
                FROM compacted_summaries
                WHERE period = 'daily'
                  AND date_range_end < datetime('now', '-7 days')
                GROUP BY agent_id, strftime('%Y-%W', date_range_start)
                """
            ).fetchall()

            for row in rows:
                row = dict(row)
                existing = conn.execute(
                    """
                    SELECT id FROM compacted_summaries
                    WHERE period = 'weekly' AND agent_id = ?
                      AND strftime('%Y-%W', date_range_start) = ?
                    """,
                    (row["agent_id"], row["week"]),
                ).fetchone()

                if existing:
                    continue

                summary = _truncate_at_sentence(row["combined"], SUMMARY_BUDGET)

                if not dry_run:
                    conn.execute(
                        """
                        INSERT INTO compacted_summaries
                        (period, agent_id, summary, signal_count, date_range_start, date_range_end)
                        VALUES ('weekly', ?, ?, ?, ?, ?)
                        """,
                        (row["agent_id"], summary, row["total_count"],
                         row["range_start"], row["range_end"]),
                    )
                    conn.execute(
                        """
                        DELETE FROM compacted_summaries
                        WHERE period = 'daily' AND agent_id = ?
                          AND date_range_end < datetime('now', '-7 days')
                          AND strftime('%Y-%W', date_range_start) = ?
                        """,
                        (row["agent_id"], row["week"]),
                    )

                result["digests_created"] += 1

        return result

    def _compact_monthly(self, dry_run: bool) -> Dict:
        """Merge weekly digests older than 30 days into monthly snapshots."""
        result = {"snapshots_created": 0}

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_id,
                       strftime('%Y-%m', date_range_start) as month,
                       GROUP_CONCAT(summary, ' | ') as combined,
                       SUM(signal_count) as total_count,
                       MIN(date_range_start) as range_start,
                       MAX(date_range_end) as range_end
                FROM compacted_summaries
                WHERE period = 'weekly'
                  AND date_range_end < datetime('now', '-30 days')
                GROUP BY agent_id, strftime('%Y-%m', date_range_start)
                """
            ).fetchall()

            for row in rows:
                row = dict(row)
                existing = conn.execute(
                    """
                    SELECT id FROM compacted_summaries
                    WHERE period = 'monthly' AND agent_id = ?
                      AND strftime('%Y-%m', date_range_start) = ?
                    """,
                    (row["agent_id"], row["month"]),
                ).fetchone()

                if existing:
                    continue

                summary = _truncate_at_sentence(row["combined"], SUMMARY_BUDGET)

                if not dry_run:
                    conn.execute(
                        """
                        INSERT INTO compacted_summaries
                        (period, agent_id, summary, signal_count, date_range_start, date_range_end)
                        VALUES ('monthly', ?, ?, ?, ?, ?)
                        """,
                        (row["agent_id"], summary, row["total_count"],
                         row["range_start"], row["range_end"]),
                    )
                    conn.execute(
                        """
                        DELETE FROM compacted_summaries
                        WHERE period = 'weekly' AND agent_id = ?
                          AND date_range_end < datetime('now', '-30 days')
                          AND strftime('%Y-%m', date_range_start) = ?
                        """,
                        (row["agent_id"], row["month"]),
                    )

                result["snapshots_created"] += 1

        return result

    def get_history(self, days: int = 30, agent: Optional[str] = None) -> List[Dict]:
        """
        Return compacted summaries for a time range.

        Args:
            days: How far back to look (default 30)
            agent: Filter by agent_id (optional)

        Returns:
            List of summary dicts, newest first.
        """
        with self.db.connect() as conn:
            if agent:
                rows = conn.execute(
                    """
                    SELECT period, agent_id, summary, signal_count,
                           date_range_start, date_range_end, created_at
                    FROM compacted_summaries
                    WHERE date_range_end >= datetime('now', ?)
                      AND agent_id = ?
                    ORDER BY date_range_start DESC
                    """,
                    (f"-{days} days", agent),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT period, agent_id, summary, signal_count,
                           date_range_start, date_range_end, created_at
                    FROM compacted_summaries
                    WHERE date_range_end >= datetime('now', ?)
                    ORDER BY date_range_start DESC
                    """,
                    (f"-{days} days",),
                ).fetchall()

            return [dict(row) for row in rows]
