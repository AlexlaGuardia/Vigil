"""Tests for frame detection and filtering."""

import os
import tempfile
import pytest
from vigil.db import VigilDB
from vigil.frames import Frame, FrameDetector
from vigil.signals import Signal, SignalType


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def detector(db):
    return FrameDetector(db)


class TestFrame:
    def test_matches_triggers(self):
        frame = Frame(id="backend", triggers=["api", "database", "deploy"])
        assert frame.matches("deploying the api") == 2
        assert frame.matches("nothing relevant") == 0

    def test_case_insensitive(self):
        frame = Frame(id="test", triggers=["API", "Deploy"])
        assert frame.matches("api deploy") == 2


class TestFrameDetector:
    def test_register_and_detect(self, detector):
        detector.register("backend", "Backend work", ["api", "database", "deploy"])
        detector.register("creative", "Creative work", ["story", "character", "lore"])

        assert detector.detect("working on the api") == "backend"
        assert detector.detect("writing a story") == "creative"

    def test_default_when_no_match(self, detector):
        detector.register("backend", "Backend", ["api"])
        assert detector.detect("nothing matches") == "default"

    def test_custom_default(self, db):
        detector = FrameDetector(db, default_frame="general")
        detector.register("backend", "Backend", ["api"])
        assert detector.detect("nothing matches") == "general"

    def test_highest_score_wins(self, detector):
        detector.register("backend", "Backend", ["api", "server", "deploy"])
        detector.register("frontend", "Frontend", ["react"])

        assert detector.detect("deploy the api server") == "backend"

    def test_detect_from_signals(self, detector):
        detector.register("backend", "Backend", ["api", "database"])

        signals = [
            Signal(from_agent="a", content="fixed the api endpoint"),
            Signal(from_agent="b", content="updated database schema"),
        ]
        assert detector.detect_from_signals(signals) == "backend"

    def test_empty_signals(self, detector):
        assert detector.detect_from_signals([]) == "default"
