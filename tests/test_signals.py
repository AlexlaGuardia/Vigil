"""Tests for the signal protocol."""

import os
import tempfile
import pytest
from vigil.db import VigilDB
from vigil.signals import Signal, SignalType, SignalBus, _truncate_at_sentence


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def bus(db):
    return SignalBus(db)


class TestSignalType:
    def test_budgets(self):
        assert SignalType.OBSERVATION.budget == 400
        assert SignalType.HANDOFF.budget == 600
        assert SignalType.SUMMARY.budget == 800
        assert SignalType.ALERT.budget == 300


class TestSignal:
    def test_basic_creation(self):
        sig = Signal(from_agent="test", content="hello world")
        assert sig.content == "hello world"
        assert sig.signal_type == SignalType.OBSERVATION

    def test_content_budget_enforcement(self):
        long_content = "A" * 500
        sig = Signal(from_agent="test", content=long_content)
        assert len(sig.content) <= SignalType.OBSERVATION.budget

    def test_alert_budget(self):
        long_content = "Alert! " * 100
        sig = Signal(from_agent="test", content=long_content, signal_type=SignalType.ALERT)
        assert len(sig.content) <= 300

    def test_string_signal_type(self):
        sig = Signal(from_agent="test", content="hello", signal_type="handoff")
        assert sig.signal_type == SignalType.HANDOFF

    def test_to_dict(self):
        sig = Signal(from_agent="agent1", content="test", id=1)
        d = sig.to_dict()
        assert d["from_agent"] == "agent1"
        assert d["signal_type"] == "observation"
        assert d["id"] == 1


class TestTruncation:
    def test_no_truncation_needed(self):
        assert _truncate_at_sentence("short text", 100) == "short text"

    def test_truncates_at_sentence(self):
        text = "First sentence. Second sentence. Third sentence that is very long."
        result = _truncate_at_sentence(text, 40)
        assert result.endswith(".")
        assert len(result) <= 40

    def test_hard_truncate_when_no_boundary(self):
        text = "A" * 500
        result = _truncate_at_sentence(text, 100)
        assert len(result) <= 100


class TestSignalBus:
    def test_emit_and_read(self, bus):
        sig = bus.emit(from_agent="agent1", content="test signal")
        assert sig.id is not None

        signals = bus.read(hours=1)
        assert len(signals) == 1
        assert signals[0].content == "test signal"
        assert signals[0].from_agent == "agent1"

    def test_emit_with_type(self, bus):
        sig = bus.emit(from_agent="agent1", content="handing off", signal_type="handoff")
        assert sig.signal_type == SignalType.HANDOFF

    def test_emit_with_target(self, bus):
        sig = bus.emit(from_agent="agent1", content="for you", to_agent="agent2")
        assert sig.to_agent == "agent2"

    def test_unacknowledged(self, bus):
        bus.emit(from_agent="a", content="first")
        bus.emit(from_agent="b", content="second")

        unacked = bus.unacknowledged()
        assert len(unacked) == 2

    def test_acknowledge(self, bus):
        sig = bus.emit(from_agent="a", content="will be acked")
        bus.acknowledge(sig.id)

        unacked = bus.unacknowledged()
        assert len(unacked) == 0

    def test_content_budget_enforced(self, bus):
        long_msg = "X" * 1000
        sig = bus.emit(from_agent="a", content=long_msg)
        assert len(sig.content) <= SignalType.OBSERVATION.budget
