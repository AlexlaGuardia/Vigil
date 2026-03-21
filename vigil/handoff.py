"""
Vigil Handoff Protocol — Structured agent-to-agent session continuity.

Agents end sessions with structured summaries (files touched, decisions made,
next steps). The next agent boots with full context: awareness + last handoff
+ signals since that handoff. No more "remind me what we were doing."
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from vigil.signals import SignalBus, SignalType

# Schema for handoffs table — integration pass adds this to db.py SCHEMA
HANDOFF_SCHEMA = """
-- Handoffs: structured session-to-session continuity
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    files_touched TEXT DEFAULT '[]',
    decisions TEXT DEFAULT '[]',
    next_steps TEXT DEFAULT '[]',
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_handoffs_agent ON handoffs(agent_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_ended ON handoffs(ended_at);
"""


@dataclass
class Handoff:
    """A structured session handoff record."""
    agent_id: str
    summary: str
    files_touched: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "summary": self.summary,
            "files_touched": self.files_touched,
            "decisions": self.decisions,
            "next_steps": self.next_steps,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    def to_briefing(self) -> str:
        """Compress handoff into a short briefing string."""
        lines = [f"[{self.agent_id}] {self.summary}"]
        if self.files_touched:
            lines.append(f"  Files: {', '.join(self.files_touched[:5])}")
            if len(self.files_touched) > 5:
                lines.append(f"  (+{len(self.files_touched) - 5} more)")
        if self.decisions:
            for d in self.decisions[:3]:
                lines.append(f"  Decision: {d}")
        if self.next_steps:
            for n in self.next_steps[:3]:
                lines.append(f"  Next: {n}")
        if self.ended_at:
            lines.append(f"  Ended: {self.ended_at}")
        return "\n".join(lines)


def _parse_json_list(raw: Any) -> List[str]:
    """Parse a JSON list from db, gracefully handling bad data."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _row_to_handoff(row: dict) -> Handoff:
    """Convert a db row dict to a Handoff dataclass."""
    return Handoff(
        id=row.get("id"),
        agent_id=row["agent_id"],
        summary=row.get("summary", ""),
        files_touched=_parse_json_list(row.get("files_touched")),
        decisions=_parse_json_list(row.get("decisions")),
        next_steps=_parse_json_list(row.get("next_steps")),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
    )


class HandoffProtocol:
    """
    Manages structured session handoffs between agents.

    Usage:
        proto = HandoffProtocol(db)
        # Agent ending session:
        proto.end_session("cc", "Shipped handoff module", files_touched=["handoff.py"])
        # Next agent booting:
        context = proto.resume("serberus")
    """

    def __init__(self, db):
        """
        Args:
            db: VigilDB instance
        """
        self.db = db
        self.bus = SignalBus(db)
        self._ensure_table()

    def _ensure_table(self):
        """Create handoffs table if it doesn't exist."""
        with self.db.connect() as conn:
            conn.executescript(HANDOFF_SCHEMA)

    def end_session(
        self,
        agent_id: str,
        summary: str,
        files_touched: Optional[List[str]] = None,
        decisions: Optional[List[str]] = None,
        next_steps: Optional[List[str]] = None,
        started_at: Optional[str] = None,
    ) -> Handoff:
        """
        Write a structured session handoff and emit a handoff signal.

        Args:
            agent_id: Who is handing off
            summary: What happened this session
            files_touched: Files created/modified
            decisions: Key decisions made
            next_steps: What the next agent should do
            started_at: When the session started (ISO format, defaults to now)

        Returns:
            The created Handoff record
        """
        files_touched = files_touched or []
        decisions = decisions or []
        next_steps = next_steps or []

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        started = started_at or now

        handoff_id = self.db.execute(
            "INSERT INTO handoffs (agent_id, summary, files_touched, decisions, next_steps, started_at, ended_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                agent_id,
                summary,
                json.dumps(files_touched),
                json.dumps(decisions),
                json.dumps(next_steps),
                started,
                now,
            ),
        )

        handoff = Handoff(
            id=handoff_id,
            agent_id=agent_id,
            summary=summary,
            files_touched=files_touched,
            decisions=decisions,
            next_steps=next_steps,
            started_at=started,
            ended_at=now,
        )

        # Emit handoff signal so daemon/other agents see it
        signal_content = f"Session ended: {summary}"
        if next_steps:
            signal_content += f" | Next: {next_steps[0]}"
        self.bus.emit(
            from_agent=agent_id,
            content=signal_content,
            signal_type="handoff",
        )

        return handoff

    def get_last_handoff(self, agent_id: Optional[str] = None) -> Optional[Handoff]:
        """
        Get the most recent handoff, optionally filtered by agent.

        Args:
            agent_id: Filter to this agent's handoffs (None = any agent)

        Returns:
            Most recent Handoff or None
        """
        if agent_id:
            row = self.db.query_one(
                "SELECT * FROM handoffs WHERE agent_id = ? ORDER BY ended_at DESC LIMIT 1",
                (agent_id,),
            )
        else:
            row = self.db.query_one(
                "SELECT * FROM handoffs ORDER BY ended_at DESC LIMIT 1"
            )
        return _row_to_handoff(row) if row else None

    def get_handoff_chain(self, limit: int = 3) -> str:
        """
        Get last N handoffs across all agents, compressed into a briefing.

        Args:
            limit: How many handoffs to include (default 3)

        Returns:
            Multi-line briefing string summarizing recent handoffs
        """
        rows = self.db.query_all(
            "SELECT * FROM handoffs ORDER BY ended_at DESC LIMIT ?",
            (limit,),
        )
        if not rows:
            return "No previous handoffs."

        handoffs = [_row_to_handoff(r) for r in rows]
        sections = [h.to_briefing() for h in handoffs]
        return "## Handoff Chain\n\n" + "\n\n".join(sections)

    def resume(self, agent_id: str) -> dict:
        """
        Build a structured boot context for an agent resuming work.

        Includes: hot awareness + last handoff + signals since that handoff.

        Args:
            agent_id: The agent that is booting

        Returns:
            Dict with awareness, last_handoff, signals_since, and pending_next_steps
        """
        from vigil.awareness import AwarenessCompiler

        # Hot awareness
        compiler = AwarenessCompiler(self.db)
        awareness = compiler.boot()

        # Last handoff (any agent — the resuming agent needs full picture)
        last = self.get_last_handoff()

        # Signals since last handoff
        signals_since = []
        if last and last.ended_at:
            rows = self.db.query_all(
                "SELECT from_agent, signal_type, content, created_at "
                "FROM signals WHERE created_at >= ? AND signal_type != 'handoff' "
                "ORDER BY created_at ASC",
                (last.ended_at,),
            )
            signals_since = [
                {
                    "from": r["from_agent"],
                    "type": r["signal_type"],
                    "content": r["content"][:200],
                    "at": r["created_at"],
                }
                for r in rows
            ]

        # Pending next steps from recent handoffs
        recent_handoffs = self.db.query_all(
            "SELECT agent_id, next_steps FROM handoffs ORDER BY ended_at DESC LIMIT 3"
        )
        pending = []
        for h in recent_handoffs:
            steps = _parse_json_list(h.get("next_steps"))
            for s in steps:
                pending.append({"from": h["agent_id"], "step": s})

        return {
            "awareness": awareness,
            "last_handoff": last.to_dict() if last else None,
            "signals_since_handoff": signals_since,
            "pending_next_steps": pending,
            "resuming_as": agent_id,
        }

    def auto_detect_stale(self, minutes: int = 30) -> List[Dict]:
        """
        Find agents with open sessions that have gone silent.

        An open session = has a handoff with no ended_at, or a session in the
        sessions table with no ended_at and no signals for N minutes.

        Uses the sessions table (existing Vigil concept) to detect staleness.

        Args:
            minutes: Silence threshold in minutes

        Returns:
            List of dicts with agent_id, session_id, last_activity, silent_minutes
        """
        # Find open sessions (no ended_at)
        open_sessions = self.db.query_all(
            "SELECT id, agent_id, started_at FROM sessions WHERE ended_at IS NULL"
        )

        stale = []
        now = datetime.now(timezone.utc)

        for session in open_sessions:
            agent = session["agent_id"]

            # Find most recent signal from this agent
            last_signal = self.db.query_one(
                "SELECT created_at FROM signals WHERE from_agent = ? ORDER BY created_at DESC LIMIT 1",
                (agent,),
            )

            # Most recent activity: latest of session start or last signal
            if last_signal and last_signal["created_at"]:
                last_activity = last_signal["created_at"]
            else:
                last_activity = session["started_at"]

            # Parse and compare
            try:
                activity_time = datetime.fromisoformat(last_activity)
                if activity_time.tzinfo is None:
                    activity_time = activity_time.replace(tzinfo=timezone.utc)
                silent = (now - activity_time).total_seconds() / 60
                if silent >= minutes:
                    stale.append({
                        "agent_id": agent,
                        "session_id": session["id"],
                        "last_activity": last_activity,
                        "silent_minutes": round(silent, 1),
                    })
            except (ValueError, TypeError):
                # Can't parse timestamp — flag as stale to be safe
                stale.append({
                    "agent_id": agent,
                    "session_id": session["id"],
                    "last_activity": last_activity,
                    "silent_minutes": -1,
                })

        return stale
