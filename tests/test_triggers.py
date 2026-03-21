"""Tests for the Vigil trigger engine."""

import os
import tempfile
import pytest
from vigil.db import VigilDB
from vigil.signals import Signal, SignalType, SignalBus
from vigil.triggers import Trigger, TriggerEngine


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def bus(db):
    return SignalBus(db)


@pytest.fixture
def engine(db, bus):
    return TriggerEngine(db, bus)


class TestTriggerMatching:
    def test_matches_any(self):
        t = Trigger(name="all", action_type="log")
        sig = Signal(from_agent="test", content="hello")
        assert t.matches(sig)

    def test_matches_signal_type(self):
        t = Trigger(name="alerts", action_type="log", signal_type="alert")
        assert t.matches(Signal(from_agent="x", content="fire!", signal_type=SignalType.ALERT))
        assert not t.matches(Signal(from_agent="x", content="hey", signal_type=SignalType.OBSERVATION))

    def test_matches_agent_exact(self):
        t = Trigger(name="from-bob", action_type="log", agent_pattern="bob")
        assert t.matches(Signal(from_agent="bob", content="hi"))
        assert not t.matches(Signal(from_agent="alice", content="hi"))

    def test_matches_agent_glob(self):
        t = Trigger(name="backend", action_type="log", agent_pattern="backend-*")
        assert t.matches(Signal(from_agent="backend-api", content="x"))
        assert t.matches(Signal(from_agent="backend-worker", content="x"))
        assert not t.matches(Signal(from_agent="frontend-ui", content="x"))

    def test_matches_content_pattern(self):
        t = Trigger(name="deploy", action_type="log", content_pattern=r"deploy|shipped")
        assert t.matches(Signal(from_agent="x", content="just deployed v2"))
        assert t.matches(Signal(from_agent="x", content="shipped new feature"))
        assert not t.matches(Signal(from_agent="x", content="working on tests"))

    def test_matches_content_case_insensitive(self):
        t = Trigger(name="err", action_type="log", content_pattern=r"error|fail")
        assert t.matches(Signal(from_agent="x", content="ERROR: something broke"))
        assert t.matches(Signal(from_agent="x", content="Build FAILED"))

    def test_disabled_never_matches(self):
        t = Trigger(name="off", action_type="log", enabled=False)
        assert not t.matches(Signal(from_agent="x", content="hello"))

    def test_combined_filters(self):
        t = Trigger(name="strict", action_type="log",
                    signal_type="alert", agent_pattern="monitor-*",
                    content_pattern=r"latency")
        # All match
        assert t.matches(Signal(from_agent="monitor-api", content="latency spike!",
                                signal_type=SignalType.ALERT))
        # Wrong type
        assert not t.matches(Signal(from_agent="monitor-api", content="latency spike!",
                                    signal_type=SignalType.OBSERVATION))
        # Wrong agent
        assert not t.matches(Signal(from_agent="backend-api", content="latency spike!",
                                    signal_type=SignalType.ALERT))
        # Wrong content
        assert not t.matches(Signal(from_agent="monitor-api", content="all good",
                                    signal_type=SignalType.ALERT))


class TestTriggerRegistration:
    def test_register(self, engine):
        t = engine.register("test-trigger", action_type="log")
        assert t.name == "test-trigger"
        assert t.id is not None

    def test_list_triggers(self, engine):
        engine.register("a", action_type="log")
        engine.register("b", action_type="log")
        triggers = engine.list_triggers()
        assert len(triggers) == 2

    def test_remove(self, engine):
        engine.register("temp", action_type="log")
        engine.remove("temp")
        assert len(engine.list_triggers()) == 0

    def test_toggle(self, engine):
        engine.register("toggle-test", action_type="log")
        engine.toggle("toggle-test", enabled=False)
        assert len(engine.list_triggers(enabled_only=True)) == 0
        assert len(engine.list_triggers(enabled_only=False)) == 1
        engine.toggle("toggle-test", enabled=True)
        assert len(engine.list_triggers(enabled_only=True)) == 1

    def test_register_with_config(self, engine):
        t = engine.register(
            "webhook-test",
            action_type="webhook",
            action_config={"url": "https://example.com/hook"},
            signal_type="alert",
            agent_pattern="monitor-*",
            content_pattern=r"latency",
        )
        triggers = engine.list_triggers()
        assert len(triggers) == 1
        assert triggers[0].action_config["url"] == "https://example.com/hook"
        assert triggers[0].signal_type == "alert"
        assert triggers[0].agent_pattern == "monitor-*"


class TestActionSignal:
    def test_fires_signal(self, engine, bus):
        engine.register("echo", action_type="signal",
                        action_config={"agent": "echo-bot", "content": "Echoing: {content}"})
        sig = Signal(from_agent="user", content="hello world")
        results = engine.evaluate(sig)
        assert len(results) == 1
        assert "signal emitted" in results[0]["result"]

        # Check the echo signal was created
        signals = bus.read(hours=1, limit=10)
        echo = [s for s in signals if s.from_agent == "echo-bot"]
        assert len(echo) == 1
        assert "hello world" in echo[0].content


class TestActionFocus:
    def test_fires_focus(self, engine, db):
        engine.register("alert-focus", action_type="focus",
                        signal_type="alert",
                        action_config={"description": "ALERT from {agent}: {content}", "priority": 1})
        sig = Signal(from_agent="monitor", content="API down!", signal_type=SignalType.ALERT)
        results = engine.evaluate(sig)
        assert len(results) == 1
        assert "focus added" in results[0]["result"]

        focus = db.get_active_focus(limit=10)
        assert len(focus) == 1
        assert focus[0]["priority"] == 1
        assert "monitor" in focus[0]["description"]


class TestActionLog:
    def test_fires_log(self, engine):
        engine.register("logger", action_type="log")
        sig = Signal(from_agent="test", content="something happened")
        results = engine.evaluate(sig)
        assert len(results) == 1
        assert "test" in results[0]["result"]


class TestEvaluate:
    def test_no_triggers(self, engine):
        sig = Signal(from_agent="x", content="hello")
        assert engine.evaluate(sig) == []

    def test_no_match(self, engine):
        engine.register("alerts-only", action_type="log", signal_type="alert")
        sig = Signal(from_agent="x", content="hello")  # observation, not alert
        assert engine.evaluate(sig) == []

    def test_multiple_matches(self, engine):
        engine.register("all-signals", action_type="log")
        engine.register("alerts", action_type="log", signal_type="alert")
        sig = Signal(from_agent="x", content="fire!", signal_type=SignalType.ALERT)
        results = engine.evaluate(sig)
        assert len(results) == 2

    def test_fire_count_increments(self, engine):
        engine.register("counter", action_type="log")
        for _ in range(3):
            engine.evaluate(Signal(from_agent="x", content="ping"))
        triggers = engine.list_triggers()
        assert triggers[0].fire_count == 3
        assert triggers[0].last_fired_at is not None


class TestToDict:
    def test_serialization(self):
        t = Trigger(name="test", action_type="webhook",
                    action_config={"url": "https://example.com"},
                    signal_type="alert", agent_pattern="backend-*",
                    content_pattern=r"error", fire_count=5)
        d = t.to_dict()
        assert d["name"] == "test"
        assert d["action_config"]["url"] == "https://example.com"
        assert d["fire_count"] == 5
