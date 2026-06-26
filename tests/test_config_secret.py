"""The hosted session secret must never fall back to a known literal: fail
closed in production, random in dev."""

import importlib
import os
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_production_without_secret_refuses_to_start():
    env = {k: v for k, v in os.environ.items() if k != "VIGIL_SESSION_SECRET"}
    env["VIGIL_ENV"] = "production"
    r = subprocess.run(
        [sys.executable, "-c", "import hosted.config"],
        env=env, cwd=_REPO_ROOT, capture_output=True,
    )
    assert r.returncode != 0
    assert b"VIGIL_SESSION_SECRET must be set" in r.stderr


def test_dev_mints_a_random_secret_not_the_old_literal(monkeypatch):
    monkeypatch.delenv("VIGIL_SESSION_SECRET", raising=False)
    monkeypatch.setenv("VIGIL_ENV", "development")
    import hosted.config as cfg
    importlib.reload(cfg)
    assert cfg.SESSION_SECRET != "change-me-in-production"
    assert len(cfg.SESSION_SECRET) >= 20


def test_explicit_secret_is_honored(monkeypatch):
    monkeypatch.setenv("VIGIL_SESSION_SECRET", "a-real-deployment-secret-value")
    monkeypatch.setenv("VIGIL_ENV", "production")
    import hosted.config as cfg
    importlib.reload(cfg)
    assert cfg.SESSION_SECRET == "a-real-deployment-secret-value"
