"""
Vigil Signal Protocol — Lightweight event bus for agent communication.

Signals are short, categorized messages that agents emit and the daemon
synthesizes into awareness. Content budgets prevent runaway data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    """Signal categories with content budgets."""
    OBSERVATION = "observation"  # 400 chars — regular activity
    HANDOFF = "handoff"          # 600 chars — session conclusions
    SUMMARY = "summary"          # 800 chars — comprehensive summaries
    ALERT = "alert"              # 300 chars — urgent notifications

    @property
    def budget(self) -> int:
        """Max content length for this signal type."""
        budgets = {
            "observation": 400,
            "handoff": 600,
            "summary": 800,
            "alert": 300,
        }
        return budgets[self.value]


@dataclass
class Signal:
    """A signal emitted by an agent."""
    from_agent: str
    content: str
    signal_type: SignalType = SignalType.OBSERVATION
    to_agent: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    acknowledged: bool = False

    def __post_init__(self):
        """Enforce content budget, truncating at sentence boundary."""
        if isinstance(self.signal_type, str):
            self.signal_type = SignalType(self.signal_type)
        budget = self.signal_type.budget
        if len(self.content) > budget:
            self.content = _truncate_at_sentence(self.content, budget)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "signal_type": self.signal_type.value,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "acknowledged": self.acknowledged,
        }


def _truncate_at_sentence(text: str, limit: int) -> str:
    """Truncate text at the last sentence boundary within limit."""
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    # Find last sentence boundary
    for sep in [". ", ".\n", "\n"]:
        idx = truncated.rfind(sep)
        if idx > limit // 2:
            return truncated[: idx + 1].rstrip()
    return truncated.rstrip()


class SignalBus:
    """
    Signal bus backed by VigilDB.

    Agents emit signals, the daemon reads and acknowledges them.
    """

    def __init__(self, db):
        """
        Args:
            db: VigilDB instance
        """
        self.db = db

    def emit(
        self,
        from_agent: str,
        content: str,
        signal_type: str = "observation",
        to_agent: Optional[str] = None,
    ) -> Signal:
        """
        Emit a signal from an agent.

        Args:
            from_agent: Agent identifier
            content: Signal content (auto-truncated to budget)
            signal_type: One of: observation, handoff, summary, alert
            to_agent: Optional target agent

        Returns:
            The created Signal with id set
        """
        sig = Signal(
            from_agent=from_agent,
            content=content,
            signal_type=SignalType(signal_type),
            to_agent=to_agent,
        )
        sig.id = self.db.create_signal(
            from_agent=sig.from_agent,
            content=sig.content,
            signal_type=sig.signal_type.value,
            to_agent=sig.to_agent,
        )
        return sig

    def read(self, hours: int = 1, limit: int = 10) -> list[Signal]:
        """Read recent signals."""
        rows = self.db.get_recent_signals(hours=hours, limit=limit)
        return [
            Signal(
                id=r["id"],
                from_agent=r["from_agent"],
                content=r["content"],
                signal_type=SignalType(r["signal_type"]),
                to_agent=r.get("to_agent"),
                created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else None,
            )
            for r in rows
        ]

    def unacknowledged(self, limit: int = 10) -> list[Signal]:
        """Read unacknowledged signals."""
        rows = self.db.get_unacknowledged_signals(limit=limit)
        return [
            Signal(
                id=r["id"],
                from_agent=r["from_agent"],
                content=r["content"],
                signal_type=SignalType(r["signal_type"]),
                to_agent=r.get("to_agent"),
                created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else None,
            )
            for r in rows
        ]

    def acknowledge(self, signal_id: int):
        """Mark a signal as processed by the daemon."""
        self.db.acknowledge_signal(signal_id)
