"""Tests for vigil.broadcast — WebSocket signal broadcasting."""

import asyncio
import json
import pytest

from vigil.broadcast import SignalBroadcaster, TenantBroadcasters


# ── Mock WebSocket ───────────────────────────────────────────────

class MockWebSocket:
    """Minimal WebSocket mock for testing."""

    def __init__(self, fail_on_send=False):
        self.accepted = False
        self.messages = []
        self.closed = False
        self.fail_on_send = fail_on_send

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        if self.fail_on_send:
            raise ConnectionError("connection lost")
        self.messages.append(json.loads(data))

    async def send_json(self, data: dict):
        if self.fail_on_send:
            raise ConnectionError("connection lost")
        self.messages.append(data)


# ── SignalBroadcaster tests ──────────────────────────────────────

class TestSignalBroadcaster:
    @pytest.fixture
    def broadcaster(self):
        return SignalBroadcaster()

    async def test_connect(self, broadcaster):
        ws = MockWebSocket()
        await broadcaster.connect(ws)
        assert ws.accepted
        assert broadcaster.connection_count == 1

    async def test_disconnect(self, broadcaster):
        ws = MockWebSocket()
        await broadcaster.connect(ws)
        await broadcaster.disconnect(ws)
        assert broadcaster.connection_count == 0

    async def test_broadcast_to_all(self, broadcaster):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await broadcaster.connect(ws1)
        await broadcaster.connect(ws2)

        await broadcaster.broadcast({"from_agent": "test", "content": "hello"})

        assert len(ws1.messages) == 1
        assert len(ws2.messages) == 1
        assert ws1.messages[0]["content"] == "hello"

    async def test_broadcast_with_agent_filter(self, broadcaster):
        ws_all = MockWebSocket()
        ws_filtered = MockWebSocket()
        await broadcaster.connect(ws_all, agent_filter="")
        await broadcaster.connect(ws_filtered, agent_filter="backend")

        await broadcaster.broadcast({"from_agent": "frontend", "content": "hello"})

        assert len(ws_all.messages) == 1
        assert len(ws_filtered.messages) == 0  # filtered out

        await broadcaster.broadcast({"from_agent": "backend", "content": "world"})

        assert len(ws_all.messages) == 2
        assert len(ws_filtered.messages) == 1

    async def test_broadcast_removes_dead_connections(self, broadcaster):
        ws_good = MockWebSocket()
        ws_dead = MockWebSocket(fail_on_send=True)
        await broadcaster.connect(ws_good)
        await broadcaster.connect(ws_dead)

        assert broadcaster.connection_count == 2

        await broadcaster.broadcast({"from_agent": "test", "content": "hello"})

        assert broadcaster.connection_count == 1
        assert len(ws_good.messages) == 1

    async def test_broadcast_no_connections(self, broadcaster):
        # Should not raise
        await broadcaster.broadcast({"from_agent": "test", "content": "hello"})

    async def test_multiple_disconnects(self, broadcaster):
        ws = MockWebSocket()
        await broadcaster.connect(ws)
        await broadcaster.disconnect(ws)
        await broadcaster.disconnect(ws)  # Should not raise
        assert broadcaster.connection_count == 0


# ── TenantBroadcasters tests ────────────────────────────────────

class TestTenantBroadcasters:
    @pytest.fixture
    def tenants(self):
        return TenantBroadcasters()

    async def test_get_creates_broadcaster(self, tenants):
        b = tenants.get("project-1")
        assert isinstance(b, SignalBroadcaster)
        assert tenants.get("project-1") is b  # Same instance

    async def test_tenant_isolation(self, tenants):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()

        b1 = tenants.get("project-1")
        b2 = tenants.get("project-2")
        await b1.connect(ws1)
        await b2.connect(ws2)

        await tenants.broadcast("project-1", {"content": "for project 1"})

        assert len(ws1.messages) == 1
        assert len(ws2.messages) == 0  # Different tenant

    async def test_total_connections(self, tenants):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await tenants.get("p1").connect(ws1)
        await tenants.get("p2").connect(ws2)
        assert tenants.total_connections == 2

    async def test_broadcast_nonexistent_tenant(self, tenants):
        # Should not raise
        await tenants.broadcast("nonexistent", {"content": "test"})
