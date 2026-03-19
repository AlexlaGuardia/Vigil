---
title: "I Built a Nervous System for AI Agents (Not Another Memory Store)"
published: false
description: "Why your AI agents need awareness, not just memory — and how frame-based tool filtering saved me 50K+ tokens per session."
tags: ai, python, mcp, opensource
cover_image:
---

## The Problem Nobody Talks About

Everyone's building AI agents. Nobody's building the infrastructure to keep them aware.

I've been running ~95 MCP tools across multiple AI agents for the past year — a coding assistant, a trading system, a creative writing setup. Three problems kept hitting me:

**1. Cold starts.** Every new session starts from zero. "Remind me what we were working on" is the most common first message. The agent has no idea what happened 5 minutes ago in a different session.

**2. Token bloat.** Loading 95 tool definitions into context burns ~50,000 tokens before the agent does a single useful thing. That's real money and real context window wasted on tools the agent won't use in this session.

**3. No coordination.** I have multiple agents working on different parts of the same system. They can't hand off work or share awareness without me copy-pasting context between them.

The existing tools (Mem0, Letta, LangGraph) solve pieces of this. Mem0 does memory retrieval. Letta does stateful agents. LangGraph does workflow state. But none of them give agents **awareness** — a continuously-compiled understanding of what's happening right now.

## What If Agents Had a Nervous System?

Memory stores are filing cabinets. You put stuff in, you pull stuff out. That's useful, but it's not how awareness works.

Your nervous system doesn't wait for you to query it. It continuously processes signals from your environment and compiles them into a state that's instantly available. You don't boot up every morning and run `SELECT * FROM memories WHERE relevant = true`. You just... know what's going on.

That's what I built.

## Vigil: Three Ideas That Changed Everything

### 1. The Awareness Daemon

A background process runs every 90 seconds, reading recent signals from agents and compiling them into "hot context" — a structured JSON blob that any agent can boot from instantly.

```python
from vigil import VigilDaemon

daemon = VigilDaemon(
    db_path="vigil.db",
    compile_interval=90,
    awareness_file="AWARENESS.md",
)
daemon.start()  # Background thread
```

When an agent starts a new session, it doesn't cold-start. It calls `compiler.boot()` and gets full context in <1 second: what frame it's in, what's being worked on, what signals came in recently, what the priority queue looks like.

The daemon also writes an `AWARENESS.md` file — human-readable, version-controllable awareness state. My agents and I read the same file.

### 2. Frame-Based Tool Filtering

This was the biggest win. Instead of loading all tools into every context, you tag tools with "frames" — named context modes.

```python
from vigil.registry import tool, tool_count

@tool(name="deploy", description="Deploy to production",
      frames=["backend", "devops"])
async def deploy(args):
    ...

@tool(name="write_chapter", description="Write a story chapter",
      frames=["creative"])
async def write_chapter(args):
    ...

@tool(name="health", description="Health check",
      frames=["core"])  # Always visible
async def health(args):
    ...

# The magic
tool_count()              # 3 (all tools)
tool_count("backend")     # 2 (deploy + health)
tool_count("creative")    # 2 (write_chapter + health)
```

An agent in "backend" mode never sees creative writing tools. An agent in "creative" mode never sees deployment tools. The `core` frame tag makes tools visible everywhere.

In my setup, this took tool definitions from 95 (all) down to 14-25 per session depending on context. That's a **75-85% reduction** in tool-definition tokens. The LLM also makes better tool choices because it has fewer irrelevant options.

The daemon auto-detects the active frame from recent signals using keyword matching. If agents are talking about "api" and "database," you're in backend mode. If they're talking about "story" and "character," you're in creative mode.

### 3. Signal Protocol

Agents communicate through signals — short, categorized messages with content budgets:

| Type | Budget | Purpose |
|------|--------|---------|
| observation | 400 chars | Regular activity updates |
| handoff | 600 chars | Session conclusions |
| summary | 800 chars | Comprehensive summaries |
| alert | 300 chars | Urgent notifications |

```python
from vigil import SignalBus, VigilDB

db = VigilDB("vigil.db")
bus = SignalBus(db)

bus.emit("backend-agent", "Deployed auth service v2. Tests passing.")
bus.emit("frontend-agent", "Dashboard layout refactored for mobile.")
```

Content budgets prevent runaway data. An observation can't be more than 400 characters. If it's longer, it gets truncated at the nearest sentence boundary. This keeps the signal-to-noise ratio high.

The daemon reads these signals, synthesizes them into the awareness summary, acknowledges them, and moves on. Agents don't talk to each other directly — they emit signals into the bus and the daemon handles synthesis.

## Architecture

```
Agents emit signals → SQLite → Daemon compiles → Hot context → Agents boot instantly
                                    ↓
                            Frame detection
                            Awareness synthesis
                            Focus queue
```

The entire thing runs on SQLite. No Redis, no Postgres, no Docker, no infrastructure. `pip install vigil-agent` and you have a working cognitive layer.

## Why Not [Existing Tool]?

| | Vigil | Mem0 | Letta | LangGraph |
|---|---|---|---|---|
| Approach | Awareness daemon | Memory retrieval | Stateful runtime | State machine |
| Context | Pre-compiled, instant | Query on demand | LLM-managed | Checkpoint-based |
| Tool filtering | Frame-based | None | None | None |
| Multi-agent | Signal protocol | Shared memory | Single agent | Graph edges |
| Infra | SQLite | API + LLM costs | Full runtime | LangChain ecosystem |

These aren't competitors — they're complementary. Vigil handles awareness and coordination. Mem0 handles deep memory. Use both if you want.

## Quick Start

```bash
pip install vigil-agent
vigil init
vigil signal my-agent "Starting work on the auth system"
vigil daemon start
```

Or in Python:

```python
from vigil import VigilDB, SignalBus, AwarenessCompiler

db = VigilDB("vigil.db")
bus = SignalBus(db)
compiler = AwarenessCompiler(db)

bus.emit("agent", "Deployed new API endpoint")
compiler.synthesize()
context = compiler.compile()

# Next session, any agent can boot with:
hot_context = compiler.boot()  # <1 second, full awareness
```

48 tests. MIT license. Zero dependencies beyond Python stdlib.

**GitHub:** [github.com/AlexlaGuardia/Vigil](https://github.com/AlexlaGuardia/Vigil)

---

*This is v0.1.0. The roadmap includes session handoff protocol, conversation compaction, and a hosted dashboard for teams. If you're building multi-agent systems and fighting the same problems, I'd love to hear how you're solving them.*
