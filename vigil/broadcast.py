"""
Signal Broadcaster — WebSocket pub/sub for real-time signal streaming.

Manages WebSocket connections and broadcasts new signals to all
connected clients. Used by both self-hosted and hosted tiers.

Usage:
    broadcaster = SignalBroadcaster()

    # In WebSocket endpoint
    await broadcaster.connect(websocket)

    # When signal is emitted
    await broadcaster.broadcast({"signal_id": 1, "content": "..."})
"""

import asyncio
import json
from typing import Optional


class SignalBroadcaster:
    """Manages WebSocket connections for real-time signal streaming.

    Thread-safe via asyncio. Each connection can optionally filter by agent.
    """

    def __init__(self):
        # Set of (websocket, agent_filter) tuples
        self._connections: set = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket, agent_filter: str = ""):
        """Accept and register a WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
            agent_filter: Only send signals from this agent (empty = all)
        """
        await websocket.accept()
        async with self._lock:
            self._connections.add((websocket, agent_filter))

    async def disconnect(self, websocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections = {
                (ws, f) for ws, f in self._connections if ws is not websocket
            }

    async def broadcast(self, signal_data: dict):
        """Send signal data to all connected clients.

        Automatically removes dead connections.
        """
        if not self._connections:
            return

        dead = set()
        agent = signal_data.get("from_agent", "")
        message = json.dumps(signal_data, default=str)

        async with self._lock:
            for ws, agent_filter in self._connections:
                # Skip if client is filtering and this signal doesn't match
                if agent_filter and agent != agent_filter:
                    continue
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.add((ws, agent_filter))

            if dead:
                self._connections -= dead

    @property
    def connection_count(self) -> int:
        return len(self._connections)


class TenantBroadcasters:
    """Manages per-tenant SignalBroadcasters for the hosted tier.

    Lazily creates broadcasters for each project_id.
    """

    def __init__(self):
        self._broadcasters: dict[str, SignalBroadcaster] = {}

    def get(self, project_id: str) -> SignalBroadcaster:
        """Get or create a broadcaster for a project."""
        if project_id not in self._broadcasters:
            self._broadcasters[project_id] = SignalBroadcaster()
        return self._broadcasters[project_id]

    async def broadcast(self, project_id: str, signal_data: dict):
        """Broadcast to a specific tenant's connections."""
        broadcaster = self._broadcasters.get(project_id)
        if broadcaster:
            await broadcaster.broadcast(signal_data)

    @property
    def total_connections(self) -> int:
        return sum(b.connection_count for b in self._broadcasters.values())
