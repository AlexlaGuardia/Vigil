"""
Vigil Frames — Context-aware mode switching.

Frames control which tools agents see, reducing token overhead
by 50-90% compared to loading all tools in every context.
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Frame:
    """A context mode that controls tool visibility."""
    id: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)

    def matches(self, text: str) -> int:
        """
        Score how well this frame matches the given text.

        Returns:
            Number of trigger keyword matches (0 = no match)
        """
        text_lower = text.lower()
        return sum(1 for t in self.triggers if t.lower() in text_lower)


class FrameDetector:
    """
    Detect the active frame from recent signals.

    Uses keyword matching against registered frame triggers.
    Falls back to default frame when no match is found.
    """

    def __init__(self, db, default_frame: str = "default"):
        """
        Args:
            db: VigilDB instance
            default_frame: Frame to use when no triggers match
        """
        self.db = db
        self.default_frame = default_frame

    def register(self, frame_id: str, description: str = "", triggers: list[str] = None):
        """
        Register a frame with trigger keywords.

        Args:
            frame_id: Unique frame identifier
            description: Human-readable description
            triggers: Keywords that activate this frame
        """
        self.db.register_frame(frame_id, description, triggers or [])

    def detect(self, text: str) -> str:
        """
        Detect the best frame for the given text.

        Scores each frame's triggers against the text.
        Returns the highest-scoring frame, or default if none match.

        Args:
            text: Text to match against (typically concatenated recent signals)

        Returns:
            Frame ID string
        """
        frames_data = self.db.get_frames()
        if not frames_data:
            return self.default_frame

        frames = [
            Frame(id=f["id"], description=f.get("description", ""), triggers=f.get("triggers", []))
            for f in frames_data
        ]

        scores = {f.id: f.matches(text) for f in frames}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else self.default_frame

    def detect_from_signals(self, signals: list) -> str:
        """
        Detect frame from a list of Signal objects.

        Args:
            signals: List of Signal objects

        Returns:
            Frame ID string
        """
        combined = " ".join(s.content for s in signals if s.content)
        return self.detect(combined)
