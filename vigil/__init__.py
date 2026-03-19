"""
Vigil — Cognitive infrastructure for AI agents.

Awareness daemon, frame-based tool filtering, and signal protocol.
"""

__version__ = "0.1.0"

from vigil.signals import Signal, SignalType, SignalBus
from vigil.frames import Frame, FrameDetector
from vigil.registry import tool, get_tools, call_tool
from vigil.awareness import AwarenessCompiler
from vigil.daemon import VigilDaemon
from vigil.db import VigilDB

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
]
