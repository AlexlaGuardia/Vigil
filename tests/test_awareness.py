"""Tests for awareness compilation."""

import os
import tempfile
import pytest
from vigil.db import VigilDB
from vigil.signals import SignalBus
from vigil.frames import FrameDetector
from vigil.awareness import AwarenessCompiler


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
def compiler(db):
    return AwarenessCompiler(db)


@pytest.fixture
def compiler_with_frames(db):
    detector = FrameDetector(db)
    detector.register("backend", "Backend", ["api", "database", "deploy"])
    return AwarenessCompiler(db, frame_detector=detector)


class TestSynthesize:
    def test_synthesize_from_signal(self, bus, compiler):
        bus.emit(from_agent="agent1", content="Deployed new API endpoint")
        assert compiler.synthesize() is True

        awareness = compiler.db.get_awareness()
        assert "Deployed new API endpoint" in awareness["summary"]

    def test_synthesize_acknowledges(self, bus, compiler):
        bus.emit(from_agent="a", content="test")
        compiler.synthesize()

        unacked = bus.unacknowledged()
        assert len(unacked) == 0

    def test_no_signals_returns_false(self, compiler):
        assert compiler.synthesize() is False


class TestCompile:
    def test_basic_compile(self, compiler):
        context = compiler.compile()
        assert "frame" in context
        assert "awareness" in context
        assert "focus" in context
        assert "compiled_at" in context

    def test_compile_with_signals(self, bus, compiler):
        bus.emit(from_agent="agent1", content="Working on API")
        compiler.synthesize()
        context = compiler.compile()
        assert context["recent_signals"] >= 0

    def test_compile_with_focus(self, compiler):
        compiler.db.add_focus("Build auth system", priority=1, owner="backend")
        context = compiler.compile()
        assert len(context["focus"]) == 1
        assert context["focus"][0]["task"] == "Build auth system"

    def test_compile_with_frame_detection(self, bus, compiler_with_frames):
        bus.emit(from_agent="a", content="Fixed the api database query")
        compiler_with_frames.synthesize()
        context = compiler_with_frames.compile()
        assert context["frame"] == "backend"

    def test_extra_context(self, compiler):
        context = compiler.compile(extra_context={"custom": "data"})
        assert context["custom"] == "data"

    def test_compile_stores_state(self, compiler):
        compiler.compile()
        state = compiler.db.get_brain_state()
        assert state is not None
        assert state["compiled_at"] is not None


class TestBoot:
    def test_boot_without_compile(self, compiler):
        context = compiler.boot()
        assert context["frame"] == "default"

    def test_boot_after_compile(self, bus, compiler):
        bus.emit(from_agent="a", content="hello")
        compiler.synthesize()
        compiler.compile()

        context = compiler.boot()
        assert "compiled_at" in context
