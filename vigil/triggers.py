"""
Vigil Event Triggers — Pattern matching on signals that fire actions.

Define rules like: "when any agent emits an alert, POST to this webhook"
or "when backend-agent hands off, update the focus queue."

Triggers are evaluated by the daemon on each compile cycle or can be
checked manually after emitting a signal.
"""

import json
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Callable, Any

from vigil.signals import Signal, SignalType, SignalBus

log = logging.getLogger("vigil.triggers")

# Schema for triggers table — included in db.py SCHEMA
TRIGGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    signal_type TEXT,
    agent_pattern TEXT DEFAULT '*',
    content_pattern TEXT,
    action_type TEXT NOT NULL,
    action_config TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    fire_count INTEGER DEFAULT 0,
    last_fired_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_triggers_enabled ON triggers(enabled);
"""


@dataclass
class Trigger:
    """A trigger rule that matches signals and fires actions."""
    name: str
    action_type: str  # "webhook", "signal", "focus", "log"
    action_config: dict = field(default_factory=dict)
    signal_type: Optional[str] = None  # None = match all types
    agent_pattern: str = "*"  # glob-style: "*", "backend-*", exact name
    content_pattern: Optional[str] = None  # regex pattern on content
    enabled: bool = True
    id: Optional[int] = None
    fire_count: int = 0
    last_fired_at: Optional[str] = None

    def matches(self, signal: Signal) -> bool:
        """Check if a signal matches this trigger's patterns."""
        if not self.enabled:
            return False

        # Type filter
        if self.signal_type and signal.signal_type.value != self.signal_type:
            return False

        # Agent pattern (glob-style)
        if self.agent_pattern != "*":
            pattern = self.agent_pattern.replace("*", ".*")
            if not re.match(f"^{pattern}$", signal.from_agent):
                return False

        # Content pattern (regex)
        if self.content_pattern:
            if not re.search(self.content_pattern, signal.content, re.IGNORECASE):
                return False

        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "signal_type": self.signal_type,
            "agent_pattern": self.agent_pattern,
            "content_pattern": self.content_pattern,
            "action_type": self.action_type,
            "action_config": self.action_config,
            "enabled": self.enabled,
            "fire_count": self.fire_count,
            "last_fired_at": self.last_fired_at,
        }


class TriggerEngine:
    """
    Evaluates signals against registered triggers and fires actions.

    Usage:
        engine = TriggerEngine(db)
        engine.register("alert-webhook", signal_type="alert",
                        action_type="webhook", action_config={"url": "https://..."})
        # On each signal:
        fired = engine.evaluate(signal)
    """

    def __init__(self, db, bus: Optional[SignalBus] = None):
        """
        Args:
            db: VigilDB instance
            bus: Optional SignalBus for "signal" action type
        """
        self.db = db
        self.bus = bus or SignalBus(db)
        self._ensure_table()
        self._action_handlers: Dict[str, Callable] = {
            "signal": self._action_signal,
            "focus": self._action_focus,
            "log": self._action_log,
        }
        # Webhook handler only if httpx available
        try:
            import httpx
            self._action_handlers["webhook"] = self._action_webhook
        except ImportError:
            pass

    def _ensure_table(self):
        """Create triggers table if it doesn't exist."""
        with self.db.connect() as conn:
            conn.executescript(TRIGGER_SCHEMA)

    def register(
        self,
        name: str,
        action_type: str,
        action_config: dict = None,
        signal_type: Optional[str] = None,
        agent_pattern: str = "*",
        content_pattern: Optional[str] = None,
    ) -> Trigger:
        """
        Register a new trigger.

        Args:
            name: Unique trigger name
            action_type: One of: webhook, signal, focus, log
            action_config: Action-specific config dict
            signal_type: Filter to this signal type (None = all)
            agent_pattern: Glob pattern for agent names (* = all)
            content_pattern: Regex pattern for signal content

        Returns:
            The created Trigger
        """
        config = action_config or {}
        tid = self.db.execute(
            "INSERT OR REPLACE INTO triggers (name, signal_type, agent_pattern, content_pattern, "
            "action_type, action_config) VALUES (?, ?, ?, ?, ?, ?)",
            (name, signal_type, agent_pattern, content_pattern, action_type, json.dumps(config)),
        )
        return Trigger(
            id=tid, name=name, action_type=action_type, action_config=config,
            signal_type=signal_type, agent_pattern=agent_pattern,
            content_pattern=content_pattern,
        )

    def remove(self, name: str):
        """Remove a trigger by name."""
        self.db.execute("DELETE FROM triggers WHERE name = ?", (name,))

    def list_triggers(self, enabled_only: bool = True) -> List[Trigger]:
        """List all triggers."""
        if enabled_only:
            rows = self.db.query_all("SELECT * FROM triggers WHERE enabled = 1 ORDER BY name")
        else:
            rows = self.db.query_all("SELECT * FROM triggers ORDER BY name")
        return [self._row_to_trigger(r) for r in rows]

    def toggle(self, name: str, enabled: bool):
        """Enable or disable a trigger."""
        self.db.execute("UPDATE triggers SET enabled = ? WHERE name = ?", (1 if enabled else 0, name))

    def evaluate(self, signal: Signal) -> List[Dict]:
        """
        Evaluate a signal against all enabled triggers and fire matching actions.

        Args:
            signal: The signal to evaluate

        Returns:
            List of fired action results [{trigger_name, action_type, result}, ...]
        """
        triggers = self.list_triggers(enabled_only=True)
        results = []

        for trigger in triggers:
            if trigger.matches(signal):
                result = self._fire(trigger, signal)
                results.append({
                    "trigger": trigger.name,
                    "action_type": trigger.action_type,
                    "result": result,
                })

        return results

    def evaluate_recent(self, hours: int = 1) -> List[Dict]:
        """
        Evaluate all recent unacknowledged signals against triggers.
        Useful for batch processing in the daemon cycle.
        """
        signals = self.bus.unacknowledged(limit=50)
        all_results = []
        for sig in signals:
            results = self.evaluate(sig)
            all_results.extend(results)
        return all_results

    def _fire(self, trigger: Trigger, signal: Signal) -> str:
        """Fire a trigger's action."""
        handler = self._action_handlers.get(trigger.action_type)
        if not handler:
            log.warning(f"Unknown action type: {trigger.action_type}")
            return f"error: unknown action type {trigger.action_type}"

        try:
            result = handler(trigger, signal)
            # Update fire count
            self.db.execute(
                "UPDATE triggers SET fire_count = fire_count + 1, "
                "last_fired_at = CURRENT_TIMESTAMP WHERE name = ?",
                (trigger.name,),
            )
            log.info(f"Trigger '{trigger.name}' fired on signal from {signal.from_agent}")
            return result
        except Exception as e:
            log.error(f"Trigger '{trigger.name}' action failed: {e}")
            return f"error: {e}"

    # ── Action handlers ───────────────────────────────────────

    def _action_signal(self, trigger: Trigger, signal: Signal) -> str:
        """Emit a new signal in response."""
        config = trigger.action_config
        agent = config.get("agent", f"trigger:{trigger.name}")
        content = config.get("content", f"Triggered by {signal.from_agent}: {signal.content[:100]}")
        stype = config.get("signal_type", "observation")

        # Template substitution
        content = content.replace("{agent}", signal.from_agent)
        content = content.replace("{content}", signal.content[:200])
        content = content.replace("{type}", signal.signal_type.value)

        self.bus.emit(from_agent=agent, content=content, signal_type=stype)
        return f"signal emitted from {agent}"

    def _action_focus(self, trigger: Trigger, signal: Signal) -> str:
        """Add a focus item in response."""
        config = trigger.action_config
        desc = config.get("description", f"[{trigger.name}] {signal.content[:100]}")
        desc = desc.replace("{agent}", signal.from_agent)
        desc = desc.replace("{content}", signal.content[:100])
        priority = config.get("priority", 3)
        owner = config.get("owner", signal.from_agent)

        self.db.add_focus(description=desc, priority=priority, owner=owner)
        return f"focus added: P{priority}"

    def _action_log(self, trigger: Trigger, signal: Signal) -> str:
        """Just log the match."""
        msg = f"[{trigger.name}] {signal.from_agent}/{signal.signal_type.value}: {signal.content[:100]}"
        log.info(msg)
        return msg

    def _action_webhook(self, trigger: Trigger, signal: Signal) -> str:
        """POST to a webhook URL."""
        import httpx
        config = trigger.action_config
        url = config.get("url")
        if not url:
            return "error: no url in action_config"

        payload = {
            "trigger": trigger.name,
            "signal": {
                "from_agent": signal.from_agent,
                "signal_type": signal.signal_type.value,
                "content": signal.content,
            },
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }
        headers = config.get("headers", {})

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=10)
            return f"webhook {resp.status_code}"
        except httpx.HTTPError as e:
            return f"webhook error: {e}"

    # ── Helpers ───────────────────────────────────────────────

    def _row_to_trigger(self, row: dict) -> Trigger:
        config = {}
        if row.get("action_config"):
            try:
                config = json.loads(row["action_config"])
            except (json.JSONDecodeError, TypeError):
                pass
        return Trigger(
            id=row.get("id"),
            name=row["name"],
            signal_type=row.get("signal_type"),
            agent_pattern=row.get("agent_pattern", "*"),
            content_pattern=row.get("content_pattern"),
            action_type=row["action_type"],
            action_config=config,
            enabled=bool(row.get("enabled", 1)),
            fire_count=row.get("fire_count", 0),
            last_fired_at=row.get("last_fired_at"),
        )
