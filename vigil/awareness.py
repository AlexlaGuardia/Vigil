"""
Vigil Awareness Compiler — Synthesizes signals into hot context.

The compiler reads recent signals, detects the active frame,
and builds a structured context object that agents can boot from
in <1 second. No startup latency, no "remind me what we were doing."
"""

import json
from datetime import datetime, timezone
from typing import Optional


class AwarenessCompiler:
    """
    Compiles system state from signals into structured hot context.

    The compile cycle:
    1. Read unacknowledged signals
    2. Synthesize awareness summary
    3. Detect active frame
    4. Build hot context JSON
    5. Store in brain_state for instant agent boot
    """

    def __init__(self, db, frame_detector=None):
        """
        Args:
            db: VigilDB instance
            frame_detector: Optional FrameDetector for automatic frame detection
        """
        self.db = db
        self.frame_detector = frame_detector

    def synthesize(self) -> bool:
        """
        Synthesize awareness from recent signals.

        Priority order:
        1. Unacknowledged signals (fresh input)
        2. Rolling summary from recent acknowledged signals
        3. Existing awareness (no change)

        Returns:
            True if awareness was updated
        """
        # Try unacknowledged signals first
        unacked = self.db.get_unacknowledged_signals(limit=1)
        if unacked:
            signal = unacked[0]
            content = signal["content"]
            self.db.update_awareness(content[:2000], updated_by="compiler")
            self.db.acknowledge_signal(signal["id"])
            return True

        # Fallback: rolling summary from recent signals
        recent = self.db.get_recent_signals(hours=6, limit=5)
        if recent:
            lines = []
            for r in recent:
                snippet = r["content"][:200].strip()
                # Trim at sentence boundary
                for sep in [". ", ".\n", "\n"]:
                    idx = snippet.rfind(sep)
                    if idx > 80:
                        snippet = snippet[: idx + 1]
                        break
                lines.append(f"- {snippet}")

            date = recent[0]["created_at"][:10] if recent[0].get("created_at") else "unknown"
            summary = f"**Session: {date} — Recent Activity**\n\n" + "\n".join(lines)

            current = self.db.get_awareness()
            if not current or current.get("summary") != summary[:2000]:
                self.db.update_awareness(summary[:2000], updated_by="compiler-rolling")
                return True

        return False

    def compile(self, extra_context: Optional[dict] = None) -> dict:
        """
        Compile full hot context for agent boot.

        This is the core product: everything an agent needs to orient,
        compiled into a single JSON object.

        Args:
            extra_context: Additional key-value pairs to include

        Returns:
            Hot context dict with frame, awareness, focus, signals, etc.
        """
        # Awareness
        awareness = self.db.get_awareness()
        awareness_text = awareness["summary"] if awareness else "No awareness"

        # Focus items
        focus = self.db.get_active_focus(limit=5)
        focus_items = [
            {"priority": f["priority"], "task": f["description"], "owner": f.get("owner")}
            for f in focus
        ]

        # Recent signals
        recent = self.db.get_recent_signals(hours=1, limit=5)

        # Frame detection
        frame = "default"
        if self.frame_detector and recent:
            from vigil.signals import Signal, SignalType
            signal_objs = [
                Signal(
                    from_agent=r["from_agent"],
                    content=r["content"],
                    signal_type=SignalType(r["signal_type"]),
                )
                for r in recent
            ]
            frame = self.frame_detector.detect_from_signals(signal_objs)

        now = datetime.now(timezone.utc).isoformat()

        context = {
            "frame": frame,
            "awareness": awareness_text,
            "focus": focus_items,
            "recent_signals": len(recent),
            "_signals": [
                {
                    "from": r["from_agent"],
                    "type": r["signal_type"],
                    "content": r["content"][:100],
                }
                for r in recent
            ],
            "compiled_at": now,
        }

        if extra_context:
            context.update(extra_context)

        # Store compiled state
        self.db.update_brain_state(frame, context)

        return context

    def boot(self) -> dict:
        """
        Get the most recently compiled hot context.

        This is what agents call on startup — instant context load
        without recompilation.

        Returns:
            Hot context dict, or empty context if never compiled
        """
        state = self.db.get_brain_state()
        if state and state.get("hot_context"):
            return state["hot_context"]
        return {"frame": "default", "awareness": "No context compiled yet", "focus": []}
