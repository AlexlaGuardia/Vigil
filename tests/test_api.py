"""Tests for the Vigil REST API."""

import os
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport
from vigil.db import VigilDB
from vigil.api import create_app


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = VigilDB(path)
    yield db
    os.unlink(path)


@pytest.fixture
def db_path(db):
    return str(db.path)


@pytest.fixture
def app(db_path):
    return create_app(db_path=db_path)


@pytest.fixture
def authed_app(db_path):
    return create_app(db_path=db_path, api_key="test-key-123")


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def authed_client(authed_app):
    transport = ASGITransport(app=authed_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealth:
    @pytest.mark.anyio
    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAuth:
    @pytest.mark.anyio
    async def test_no_auth_required_when_no_key(self, client):
        r = await client.get("/boot")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_auth_required_when_key_set(self, authed_client):
        r = await authed_client.get("/boot")
        assert r.status_code == 401

    @pytest.mark.anyio
    async def test_bearer_auth(self, authed_client):
        r = await authed_client.get("/boot", headers={"Authorization": "Bearer test-key-123"})
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_header_auth(self, authed_client):
        r = await authed_client.get("/boot", headers={"X-Vigil-Key": "test-key-123"})
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_wrong_key(self, authed_client):
        r = await authed_client.get("/boot", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401

    @pytest.mark.anyio
    async def test_health_no_auth(self, authed_client):
        """Health endpoint should work without auth."""
        r = await authed_client.get("/health")
        assert r.status_code == 200


class TestBoot:
    @pytest.mark.anyio
    async def test_boot_empty(self, client):
        r = await client.get("/boot")
        assert r.status_code == 200
        data = r.json()
        assert data["frame"] == "default"

    @pytest.mark.anyio
    async def test_boot_after_compile(self, client):
        await client.post("/signal", json={"agent": "test", "content": "hello"})
        await client.post("/compile")
        r = await client.get("/boot")
        assert r.status_code == 200


class TestSignal:
    @pytest.mark.anyio
    async def test_emit_signal(self, client):
        r = await client.post("/signal", json={"agent": "test", "content": "deployed v2"})
        assert r.status_code == 200
        data = r.json()
        assert data["signal_id"] >= 1
        assert data["type"] == "observation"

    @pytest.mark.anyio
    async def test_signal_types(self, client):
        for stype in ["observation", "handoff", "summary", "alert"]:
            r = await client.post("/signal", json={"agent": "t", "content": "x", "signal_type": stype})
            assert r.status_code == 200
            assert r.json()["type"] == stype

    @pytest.mark.anyio
    async def test_invalid_signal_type(self, client):
        r = await client.post("/signal", json={"agent": "t", "content": "x", "signal_type": "bogus"})
        assert r.status_code == 400

    @pytest.mark.anyio
    async def test_directed_signal(self, client):
        r = await client.post("/signal", json={"agent": "a", "content": "hey b", "to_agent": "b"})
        assert r.status_code == 200


class TestStatus:
    @pytest.mark.anyio
    async def test_status_empty(self, client):
        r = await client.get("/status")
        assert r.status_code == 200
        assert r.json()["status"] == "empty"

    @pytest.mark.anyio
    async def test_status_after_compile(self, client):
        await client.post("/signal", json={"agent": "t", "content": "something"})
        await client.post("/compile")
        r = await client.get("/status")
        data = r.json()
        assert "summary" in data


class TestSignals:
    @pytest.mark.anyio
    async def test_read_signals(self, client):
        await client.post("/signal", json={"agent": "a", "content": "msg 1"})
        await client.post("/signal", json={"agent": "b", "content": "msg 2"})
        r = await client.get("/signals")
        assert r.status_code == 200
        assert len(r.json()) == 2

    @pytest.mark.anyio
    async def test_filter_by_agent(self, client):
        await client.post("/signal", json={"agent": "a", "content": "from a"})
        await client.post("/signal", json={"agent": "b", "content": "from b"})
        r = await client.get("/signals", params={"agent": "a"})
        data = r.json()
        assert len(data) == 1
        assert data[0]["from_agent"] == "a"


class TestHandoff:
    @pytest.mark.anyio
    async def test_handoff(self, client):
        r = await client.post("/handoff", json={
            "agent": "test",
            "summary": "Built the API",
            "next_steps": ["Write tests"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "handed_off"
        assert data["handoff_id"] >= 1

    @pytest.mark.anyio
    async def test_handoff_with_metadata(self, client):
        r = await client.post("/handoff", json={
            "agent": "coder",
            "summary": "Refactored auth",
            "files_touched": ["auth.py", "tests.py"],
            "decisions": ["Use JWT"],
            "next_steps": ["Add rate limiting"],
        })
        assert r.status_code == 200


class TestResume:
    @pytest.mark.anyio
    async def test_resume_empty(self, client):
        r = await client.post("/resume", json={"agent": "test"})
        assert r.status_code == 200
        data = r.json()
        assert data["last_handoff"] is None

    @pytest.mark.anyio
    async def test_resume_after_handoff(self, client):
        await client.post("/handoff", json={
            "agent": "agent-1",
            "summary": "finished phase 1",
            "next_steps": ["start phase 2"],
        })
        r = await client.post("/resume", json={"agent": "agent-2"})
        data = r.json()
        assert data["last_handoff"] is not None
        assert data["last_handoff"]["agent_id"] == "agent-1"


class TestChain:
    @pytest.mark.anyio
    async def test_chain_empty(self, client):
        r = await client.get("/chain")
        assert r.status_code == 200
        assert "No previous" in r.json()["briefing"]

    @pytest.mark.anyio
    async def test_chain_after_handoffs(self, client):
        await client.post("/handoff", json={"agent": "a", "summary": "did thing 1"})
        await client.post("/handoff", json={"agent": "b", "summary": "did thing 2"})
        r = await client.get("/chain", params={"limit": 2})
        text = r.json()["briefing"]
        assert "did thing 1" in text
        assert "did thing 2" in text


class TestFocus:
    @pytest.mark.anyio
    async def test_empty_focus(self, client):
        r = await client.get("/focus")
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.anyio
    async def test_add_and_list(self, client):
        await client.post("/focus", json={"description": "Ship API", "priority": 1})
        await client.post("/focus", json={"description": "Write docs", "priority": 3})
        r = await client.get("/focus")
        data = r.json()
        assert len(data) == 2
        assert data[0]["priority"] == 1

    @pytest.mark.anyio
    async def test_complete(self, client):
        add = await client.post("/focus", json={"description": "test"})
        fid = add.json()["focus_id"]
        await client.delete(f"/focus/{fid}")
        r = await client.get("/focus")
        assert r.json() == []


class TestFrames:
    @pytest.mark.anyio
    async def test_list_frames(self, client):
        r = await client.get("/frames")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_register_frame(self, client):
        await client.post("/frames", json={
            "frame_id": "backend",
            "description": "Backend dev",
            "triggers": ["api", "database"],
        })
        r = await client.get("/frames")
        ids = [f["id"] for f in r.json()]
        assert "backend" in ids


class TestAgents:
    @pytest.mark.anyio
    async def test_agents_empty(self, client):
        r = await client.get("/agents")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    @pytest.mark.anyio
    async def test_agents_after_signals(self, client):
        await client.post("/signal", json={"agent": "alpha", "content": "hi"})
        await client.post("/signal", json={"agent": "beta", "content": "yo"})
        r = await client.get("/agents")
        assert r.json()["total"] == 2

    @pytest.mark.anyio
    async def test_single_agent(self, client):
        await client.post("/signal", json={"agent": "gamma", "content": "test"})
        r = await client.get("/agents", params={"agent": "gamma"})
        assert r.json()["from_agent"] == "gamma"

    @pytest.mark.anyio
    async def test_unknown_agent(self, client):
        r = await client.get("/agents", params={"agent": "nobody"})
        assert r.status_code == 404


class TestDashboard:
    @pytest.mark.anyio
    async def test_index(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        assert "Vigil" in r.text

    @pytest.mark.anyio
    async def test_agents_page(self, client):
        r = await client.get("/dashboard/agents")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_signals_page(self, client):
        r = await client.get("/dashboard/signals")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_handoffs_page(self, client):
        r = await client.get("/dashboard/handoffs")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_frames_page(self, client):
        r = await client.get("/dashboard/frames")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_partials_signals(self, client):
        r = await client.get("/partials/signals")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_partials_awareness(self, client):
        r = await client.get("/partials/awareness")
        assert r.status_code == 200

    @pytest.mark.anyio
    async def test_index_with_data(self, client):
        """Dashboard renders with actual data."""
        await client.post("/signal", json={"agent": "test-agent", "content": "hello world"})
        await client.post("/compile")
        r = await client.get("/")
        assert r.status_code == 200
        assert "test-agent" in r.text


class TestCompact:
    @pytest.mark.anyio
    async def test_compact_empty(self, client):
        r = await client.post("/compact")
        assert r.status_code == 200
        data = r.json()
        assert data["daily_summaries"] == 0

    @pytest.mark.anyio
    async def test_compact_dry_run(self, client):
        r = await client.post("/compact", params={"dry_run": True})
        assert r.status_code == 200
        assert r.json()["dry_run"] is True
