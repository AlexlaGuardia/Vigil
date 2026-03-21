"""
Vigil — Cognitive infrastructure for AI agents.

Awareness daemon, frame-based tool filtering, signal protocol,
session handoff, and signal compaction.
"""

__version__ = "0.5.0"

from vigil.signals import Signal, SignalType, SignalBus
from vigil.frames import Frame, FrameDetector
from vigil.registry import tool, get_tools, call_tool
from vigil.awareness import AwarenessCompiler
from vigil.daemon import VigilDaemon
from vigil.db import VigilDB
from vigil.handoff import HandoffProtocol, Handoff
from vigil.compaction import SignalCompactor
from vigil.mcp_server import create_server

__all__ = [
    "Signal",
    "SignalType",
    "SignalBus",
    "Frame",
    "FrameDetector",
    "tool",
    "get_tools",
    "call_tool",
    "AwarenessCompiler",
    "VigilDaemon",
    "VigilDB",
    "HandoffProtocol",
    "Handoff",
    "SignalCompactor",
    "create_server",
]
