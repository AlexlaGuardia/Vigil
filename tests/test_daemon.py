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
