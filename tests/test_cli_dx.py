"""Tests for DX CLI commands: version, doctor, export, quickstart, knowledge."""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch
from io import StringIO

from vigil.db import VigilDB
from vigil.signals import SignalBus
from vigil.knowledge import KnowledgeBase


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def initialized_db(db_path):
    """Create and initialize a Vigil database."""
    db = VigilDB(db_path)
    db.register_frame("default", "Default frame", [])
    return db_path


def run_cli(*args, db_path=None):
    """Run a CLI command and capture output."""
    from vigil.cli import main

    env = {}
    if db_path:
        env["VIGIL_DB"] = db_path

    captured = StringIO()
    with patch.dict(os.environ, env, clear=False):
        with patch("sys.argv", ["vigil"] + list(args)):
            with patch("sys.stdout", captured):
                try:
                    main()
                except SystemExit:
                    pass
    return captured.getvalue()


class TestVersion:
    def test_prints_version(self):
        from vigil import __version__
        output = run_cli("version")
        assert f"vigil {__version__}" in output

    def test_version_format(self):
        output = run_cli("version")
        # Should be "vigil X.Y.Z"
        parts = output.strip().split()
        assert parts[0] == "vigil"
        assert "." in parts[1]


class TestDoctor:
    def test_no_db(self, db_path):
        # Remove the file so DB doesn't exist
        os.unlink(db_path)
        missing_path = db_path + "_missing"
        output = run_cli("doctor", db_path=missing_path)
        assert "missing" in output or "Database" in output

    def test_with_db(self, initialized_db):
        output = run_cli("doctor", db_path=initialized_db)
        assert "Database" in output
        assert "Vigil" in output

    def test_shows_frames(self, initialized_db):
        output = run_cli("doctor", db_path=initialized_db)
        assert "Frames" in output

    def test_shows_deps(self, initialized_db):
        output = run_cli("doctor", db_path=initialized_db)
        assert "Dependencies" in output


class TestExport:
    def test_basic_export(self, initialized_db):
        output = run_cli("export", db_path=initialized_db)
        assert "Vigil Context Export" in output

    def test_export_includes_frames(self, initialized_db):
        output = run_cli("export", db_path=initialized_db)
        assert "Frames" in output
        assert "default" in output

    def test_export_includes_signals(self, initialized_db):
        db = VigilDB(initialized_db)
        bus = SignalBus(db)
        bus.emit(from_agent="test", content="test signal")
        output = run_cli("export", "--hours", "1", db_path=initialized_db)
        assert "Signals" in output

    def test_export_to_file(self, initialized_db):
        fd, out_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            output = run_cli("export", "-o", out_path, db_path=initialized_db)
            assert "Exported" in output
            with open(out_path) as f:
                content = f.read()
            assert "Vigil Context Export" in content
        finally:
            os.unlink(out_path)


class TestQuickstart:
    def test_creates_db(self, db_path):
        # Remove existing
        os.unlink(db_path)
        new_path = db_path
        output = run_cli("quickstart", db_path=new_path)
        assert "[1/4]" in output
        assert "[4/4]" in output
        assert "Setup complete" in output
        assert os.path.exists(new_path)

    def test_registers_frames(self, db_path):
        os.unlink(db_path)
        run_cli("quickstart", db_path=db_path)
        db = VigilDB(db_path)
        frames = db.get_frames()
        frame_ids = {f["id"] for f in frames}
        assert "backend" in frame_ids
        assert "frontend" in frame_ids
        assert "devops" in frame_ids

    def test_emits_signal(self, db_path):
        os.unlink(db_path)
        run_cli("quickstart", db_path=db_path)
        db = VigilDB(db_path)
        signals = db.get_recent_signals(hours=1)
        assert len(signals) >= 1
        assert any("quickstart" in s["content"] for s in signals)

    def test_idempotent(self, initialized_db):
        # Running quickstart on existing DB shouldn't break
        output = run_cli("quickstart", db_path=initialized_db)
        assert "already exists" in output


class TestKnowCLI:
    def test_know_basic(self, initialized_db):
        output = run_cli("know", "branch", "main", db_path=initialized_db)
        assert "Stored" in output
        assert "branch" in output

    def test_know_with_category(self, initialized_db):
        output = run_cli("know", "key1", "val1", "--category", "config", db_path=initialized_db)
        assert "config" in output

    def test_recall_finds_entry(self, initialized_db):
        run_cli("know", "deploy_target", "production", db_path=initialized_db)
        output = run_cli("recall", "deploy", db_path=initialized_db)
        assert "deploy_target" in output
        assert "production" in output

    def test_recall_no_match(self, initialized_db):
        output = run_cli("recall", "nonexistent_xyz", db_path=initialized_db)
        assert "No knowledge" in output

    def test_knowledge_list(self, initialized_db):
        run_cli("know", "a", "1", db_path=initialized_db)
        run_cli("know", "b", "2", db_path=initialized_db)
        output = run_cli("knowledge", db_path=initialized_db)
        assert "2 entries" in output

    def test_forget(self, initialized_db):
        run_cli("know", "temp", "remove_me", db_path=initialized_db)
        output = run_cli("forget", "temp", db_path=initialized_db)
        assert "Forgot" in output

    def test_forget_nonexistent(self, initialized_db):
        output = run_cli("forget", "nope", db_path=initialized_db)
        assert "No knowledge" in output
