"""Tests for the handoff protocol."""

import os
import tempfile
import time
import pytest
from vigil.db import VigilDB
from vigil.handoff import HandoffProtocol, Handoff, HANDOFF_SCHEMA, _parse_json_list, _row_to_handoff


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def proto(db):
    return HandoffProtocol(db)


class TestHandoffDataclass:
    def test_basic_creation(self):
        h = Handoff(agent_id="cc", summary="shipped feature")
        assert h.agent_id == "cc"
        assert h.summary == "shipped feature"
        assert h.files_touched == []
        assert h.decisions == []
        assert h.next_steps == []

    def test_to_dict(self):
        h = Handoff(
            agent_id="cc",
            summary="test",
            files_touched=["a.py"],
            decisions=["use sqlite"],
            next_steps=["write tests"],
            id=1,
        )
        d = h.to_dict()
        assert d["agent_id"] == "cc"
        assert d["files_touched"] == ["a.py"]
        assert d["decisions"] == ["use sqlite"]
        assert d["id"] == 1

    def test_to_briefing_minimal(self):
        h = Handoff(agent_id="cc", summary="did stuff")
        brief = h.to_briefing()
        assert "[cc] did stuff" in brief

    def test_to_briefing_full(self):
        h = Handoff(
            agent_id="serberus",
            summary="shipped handoff module",
            files_touched=["handoff.py", "test_handoff.py"],
            decisions=["separate table instead of extending sessions"],
            next_steps=["integration pass", "add to CLI"],
            ended_at="2026-03-21 22:00:00",
        )
        brief = h.to_briefing()
        assert "[serberus]" in brief
        assert "handoff.py" in brief
        assert "Decision:" in brief
        assert "Next:" in brief
        assert "Ended:" in brief

    def test_to_briefing_truncates_long_lists(self):
        h = Handoff(
            agent_id="cc",
            summary="big session",
            files_touched=[f"file{i}.py" for i in range(10)],
        )
        brief = h.to_briefing()
        assert "+5 more" in brief


class TestParseJsonList:
    def test_valid_json(self):
        assert _parse_json_list('["a", "b"]') == ["a", "b"]

    def test_already_list(self):
        assert _parse_json_list(["a"]) == ["a"]

    def test_invalid_json(self):
        assert _parse_json_list("not json") == []

    def test_none(self):
        assert _parse_json_list(None) == []

    def test_json_non_list(self):
        assert _parse_json_list('{"key": "val"}') == []


class TestEndSession:
    def test_basic_end_session(self, proto):
        handoff = proto.end_session("cc", "shipped the thing")
        assert handoff.id is not None
        assert handoff.agent_id == "cc"
        assert handoff.summary == "shipped the thing"
        assert handoff.ended_at is not None

    def test_end_session_with_metadata(self, proto):
        handoff = proto.end_session(
            agent_id="serberus",
            summary="built handoff protocol",
            files_touched=["handoff.py", "test_handoff.py"],
            decisions=["separate handoffs table"],
            next_steps=["integration pass"],
        )
        assert handoff.files_touched == ["handoff.py", "test_handoff.py"]
        assert handoff.decisions == ["separate handoffs table"]
        assert handoff.next_steps == ["integration pass"]

    def test_end_session_emits_signal(self, proto, db):
        proto.end_session("cc", "test session")
        signals = db.get_recent_signals(hours=1, limit=10)
        handoff_signals = [s for s in signals if s["signal_type"] == "handoff"]
        assert len(handoff_signals) == 1
        assert "test session" in handoff_signals[0]["content"]

    def test_signal_includes_next_step(self, proto, db):
        proto.end_session("cc", "done", next_steps=["do this next"])
        signals = db.get_recent_signals(hours=1, limit=10)
        handoff_signals = [s for s in signals if s["signal_type"] == "handoff"]
        assert "do this next" in handoff_signals[0]["content"]


class TestGetLastHandoff:
    def test_no_handoffs(self, proto):
        assert proto.get_last_handoff() is None

    def test_get_last_any_agent(self, proto):
        proto.end_session("agent1", "first")
        proto.end_session("agent2", "second")
        last = proto.get_last_handoff()
        assert last.agent_id == "agent2"
        assert last.summary == "second"

    def test_get_last_filtered_by_agent(self, proto):
        proto.end_session("agent1", "from agent1")
        proto.end_session("agent2", "from agent2")
        last = proto.get_last_handoff(agent_id="agent1")
        assert last.agent_id == "agent1"
        assert last.summary == "from agent1"


class TestGetHandoffChain:
    def test_no_handoffs(self, proto):
        chain = proto.get_handoff_chain()
        assert "No previous handoffs" in chain

    def test_chain_returns_briefing(self, proto):
        proto.end_session("cc", "first session", files_touched=["a.py"])
        proto.end_session("serberus", "second session", next_steps=["test"])
        chain = proto.get_handoff_chain(limit=2)
        assert "Handoff Chain" in chain
        assert "[cc]" in chain
        assert "[serberus]" in chain

    def test_chain_respects_limit(self, proto):
        for i in range(5):
            proto.end_session(f"agent{i}", f"session {i}")
        chain = proto.get_handoff_chain(limit=2)
        # Should have exactly 2 agent entries
        assert "[agent4]" in chain
        assert "[agent3]" in chain
        assert "[agent0]" not in chain


class TestResume:
    def test_resume_with_no_history(self, proto):
        ctx = proto.resume("cc")
        assert ctx["resuming_as"] == "cc"
        assert ctx["last_handoff"] is None
        assert ctx["signals_since_handoff"] == []
        assert ctx["pending_next_steps"] == []
        assert "awareness" in ctx

    def test_resume_includes_last_handoff(self, proto):
        proto.end_session("agent1", "did work", next_steps=["continue"])
        ctx = proto.resume("agent2")
        assert ctx["last_handoff"] is not None
        assert ctx["last_handoff"]["agent_id"] == "agent1"
        assert ctx["last_handoff"]["summary"] == "did work"

    def test_resume_captures_signals_since(self, proto, db):
        proto.end_session("agent1", "handed off")
        # Emit signals after handoff
        db.create_signal("daemon", "something happened", signal_type="observation")
        db.create_signal("daemon", "another thing", signal_type="alert")
        ctx = proto.resume("agent2")
        assert len(ctx["signals_since_handoff"]) >= 1

    def test_resume_collects_pending_next_steps(self, proto):
        proto.end_session("agent1", "session 1", next_steps=["step A", "step B"])
        proto.end_session("agent2", "session 2", next_steps=["step C"])
        ctx = proto.resume("agent3")
        steps = [p["step"] for p in ctx["pending_next_steps"]]
        assert "step C" in steps
        assert "step A" in steps

    def test_resume_includes_awareness(self, proto, db):
        db.update_awareness("system is healthy", updated_by="test")
        ctx = proto.resume("cc")
        # Awareness should be present (either compiled or from boot)
        assert ctx["awareness"] is not None


class TestAutoDetectStale:
    def test_no_open_sessions(self, proto):
        stale = proto.auto_detect_stale()
        assert stale == []

    def test_detects_stale_session(self, proto, db):
        # Create an open session (no ended_at) with old started_at
        db.execute(
            "INSERT INTO sessions (agent_id, frame, started_at) VALUES (?, ?, datetime('now', '-60 minutes'))",
            ("ghost", "backend"),
        )
        stale = proto.auto_detect_stale(minutes=30)
        assert len(stale) == 1
        assert stale[0]["agent_id"] == "ghost"
        assert stale[0]["silent_minutes"] >= 30

    def test_active_session_not_stale(self, proto, db):
        # Create an open session with recent start
        db.execute(
            "INSERT INTO sessions (agent_id, frame) VALUES (?, ?)",
            ("active", "backend"),
        )
        # Emit a recent signal
        db.create_signal("active", "still here")
        stale = proto.auto_detect_stale(minutes=30)
        assert len(stale) == 0

    def test_closed_session_ignored(self, proto, db):
        # Create a closed session (has ended_at)
        session_id = db.start_session("done_agent", "backend")
        db.end_session(session_id, "finished")
        stale = proto.auto_detect_stale(minutes=1)
        assert len(stale) == 0

    def test_custom_threshold(self, proto, db):
        db.execute(
            "INSERT INTO sessions (agent_id, frame, started_at) VALUES (?, ?, datetime('now', '-10 minutes'))",
            ("agent", "backend"),
        )
        # Not stale at 30 minutes
        assert proto.auto_detect_stale(minutes=30) == []
        # Stale at 5 minutes
        stale = proto.auto_detect_stale(minutes=5)
        assert len(stale) == 1


class TestHandoffSchema:
    def test_schema_is_valid_sql(self, db):
        """HANDOFF_SCHEMA should execute without errors."""
        with db.connect() as conn:
            conn.executescript(HANDOFF_SCHEMA)
        # Verify table exists
        row = db.query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='handoffs'"
        )
        assert row is not None

    def test_schema_idempotent(self, db):
        """Running schema twice should not error (IF NOT EXISTS)."""
        with db.connect() as conn:
            conn.executescript(HANDOFF_SCHEMA)
            conn.executescript(HANDOFF_SCHEMA)


class TestRowToHandoff:
    def test_converts_row(self):
        row = {
            "id": 1,
            "agent_id": "cc",
            "summary": "test",
            "files_touched": '["a.py"]',
            "decisions": '["chose X"]',
            "next_steps": '["do Y"]',
            "started_at": "2026-03-21 20:00:00",
            "ended_at": "2026-03-21 21:00:00",
        }
        h = _row_to_handoff(row)
        assert h.agent_id == "cc"
        assert h.files_touched == ["a.py"]
        assert h.decisions == ["chose X"]
        assert h.next_steps == ["do Y"]
