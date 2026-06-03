"""Tests for the Vigil daemon."""

import os
import tempfile
import time
import pytest
from vigil.daemon import VigilDaemon
from vigil.signals import SignalBus


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


class TestDaemon:
    def test_init(self, tmp_db):
        daemon = VigilDaemon(db_path=tmp_db, compile_interval=1)
        assert daemon.compile_interval == 1
        assert daemon.db is not None

    def test_background_start_stop(self, tmp_db):
        daemon = VigilDaemon(db_path=tmp_db, compile_interval=1)
        daemon.start()
        time.sleep(2)
        daemon.stop()

        # Should have compiled at least once
        state = daemon.db.get_brain_state()
        assert state is not None
        assert state.get("compiled_at") is not None

    def test_on_compile_hook(self, tmp_db):
        results = []

        def on_compile(ctx):
            results.append(ctx)

        daemon = VigilDaemon(db_path=tmp_db, compile_interval=1, on_compile=on_compile)
        daemon.start()
        time.sleep(2.5)
        daemon.stop()

        assert len(results) >= 1
        assert "frame" in results[0]

    def test_signals_flow_through(self, tmp_db):
        daemon = VigilDaemon(db_path=tmp_db, compile_interval=1)
        bus = SignalBus(daemon.db)

        bus.emit(from_agent="test", content="signal before daemon start")
        daemon.start()
        time.sleep(2)
        daemon.stop()

        awareness = daemon.db.get_awareness()
        assert awareness is not None
        assert len(awareness.get("summary", "")) > 0

    def test_awareness_file_output(self, tmp_db):
        fd, awareness_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)

        try:
            daemon = VigilDaemon(
                db_path=tmp_db,
                compile_interval=1,
                awareness_file=awareness_path,
            )
            daemon.start()
            time.sleep(2)
            daemon.stop()

            with open(awareness_path) as f:
                content = f.read()
            assert "# Awareness" in content
            assert "Frame" in content
        finally:
            os.unlink(awareness_path)


class TestAtomicWrite:
    """_atomic_write must never leave a partial file and must leave no temp debris."""

    def test_atomic_write_basic(self, tmp_path):
        target = tmp_path / "AWARENESS.md"
        VigilDaemon._atomic_write(str(target), "hello\nworld\n")
        assert target.read_text(encoding="utf-8") == "hello\nworld\n"
        # No leftover temp files in the directory
        assert [p.name for p in tmp_path.iterdir()] == ["AWARENESS.md"]

    def test_atomic_write_overwrites_in_place(self, tmp_path):
        target = tmp_path / "AWARENESS.md"
        target.write_text("OLD CONTENT", encoding="utf-8")
        VigilDaemon._atomic_write(str(target), "NEW CONTENT")
        assert target.read_text(encoding="utf-8") == "NEW CONTENT"
        assert len(list(tmp_path.iterdir())) == 1

    def test_atomic_write_handles_unicode(self, tmp_path):
        target = tmp_path / "AWARENESS.md"
        VigilDaemon._atomic_write(str(target), "frame → copy ✓ café")
        assert target.read_text(encoding="utf-8") == "frame → copy ✓ café"

    def test_atomic_write_preserves_old_file_on_failure(self, tmp_path, monkeypatch):
        target = tmp_path / "AWARENESS.md"
        target.write_text("GOOD", encoding="utf-8")

        def boom(*a, **k):
            raise OSError("simulated rename failure")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            VigilDaemon._atomic_write(str(target), "PARTIAL")

        # Original file untouched, and the temp file was cleaned up
        assert target.read_text(encoding="utf-8") == "GOOD"
        assert [p.name for p in tmp_path.iterdir()] == ["AWARENESS.md"]
