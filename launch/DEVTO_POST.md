---
title: "I Built a Nervous System for AI Agents (Not Another Memory Store)"
published: false
description: "Why your AI agents need awareness, not just memory — and how frame-based tool filtering, session handoff, and an MCP server changed everything."
tags: ai, python, mcp, opensource
cover_image:
---

## The Problem Nobody Talks About

Everyone's building AI agents. Nobody's building the infrastructure to keep them aware.

I've been running ~95 MCP tools across multiple AI agents for the past year — a coding assistant, a trading system, a creative writing setup. Three problems kept hitting me:

**1. Cold starts.** Every new session starts from zero. The agent has no idea what happened 5 minutes ago in a different session.

**2. Token bloat.** Loading 95 tool definitions into context burns ~50,000 tokens before the agent does a single useful thing. That's real money and real context window wasted on tools the agent won't use.

**3. No coordination.** Multiple agents working on the same system can't hand off work or share awareness without me copy-pasting context between them.

The existing tools (Mem0, Letta, LangGraph) solve pieces of this. Mem0 does memory retrieval. Letta does stateful agents. LangGraph does workflow state. But none of them give agents **awareness** — a continuously-compiled understanding of what's happening right now.

## What If Agents Had a Nervous System?

Memory stores are filing cabinets. You put stuff in, you pull stuff out. That's useful, but it's not how awareness works.

Your nervous system doesn't wait for you to query it. It continuously processes signals from your environment and compiles them into a state that's instantly available. You don't boot up every morning and run `SELECT * FROM memories WHERE relevant = true`. You just... know what's going on.

That's what I built.

## Vigil: The Six Ideas

### 1. The Awareness Daemon

A background process runs every 90 seconds, reading signals from agents and compiling them into "hot context" — a structured snapshot any agent can boot from instantly.

```python
from vigil import VigilDaemon

daemon = VigilDaemon(
    db_path="vigil.db",
    compile_interval=90,
    awareness_file="AWARENESS.md",
)
daemon.start()
```

When an agent starts a session, it calls `compiler.boot()` and gets full context in under a second: active frame, current work, recent signals, priority queue. No startup latency.

The daemon also writes an `AWARENESS.md` file — human-readable, version-controllable. My agents and I read the same file.

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

tool_count()              # 3 (all tools)
tool_count("backend")     # 2 (deploy + health)
tool_count("creative")    # 2 (write_chapter + health)
```

An agent in "backend" mode never sees creative writing tools. In my setup, this took tool definitions from 95 down to 14-25 per session — a **75-85% reduction** in tool-definition tokens. The LLM also makes better tool choices with fewer irrelevant options.

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

Content budgets prevent runaway data. The daemon reads these signals, synthesizes them into the awareness summary, and moves on. Agents don't talk to each other — they emit into the bus and the daemon handles the rest.

### 4. Session Handoff

This is what makes multi-session work actually work. Agents end sessions with structured summaries:

```python
from vigil import HandoffProtocol

proto = HandoffProtocol(db)

proto.end_session(
    agent_id="backend-agent",
    summary="Shipped auth v2 with JWT tokens",
    files_touched=["auth.py", "middleware.py"],
    decisions=["Switched from session cookies to JWT"],
    next_steps=["Add rate limiting", "Write integration tests"],
)

# Next morning, different agent resumes
context = proto.resume("morning-agent")
# Includes: last handoff, signals since, pending next steps
```

Handoff chains track continuity across sessions. The resume context tells the next agent exactly what happened, what decisions were made, and what to do next. No more "remind me what we were working on."

### 5. Signal Compaction

Signals accumulate. Without compaction, your awareness context grows forever. Vigil uses tiered retention:

- **Raw signals** — kept for 7 days
- **Daily summaries** — synthesized from raw, kept for 30 days
- **Weekly digests** — synthesized from daily, kept for 90 days
- **Monthly snapshots** — permanent archive

```bash
vigil compact --dry-run  # Preview what would be compacted
vigil compact            # Run it
```

History stays manageable without losing important context.

### 6. Event Triggers

Pattern-match on signals and fire actions automatically:

```python
from vigil import TriggerManager

triggers = TriggerManager(db)

triggers.create(
    name="alert-to-slack",
    signal_type="alert",
    agent_pattern="*",
    action_type="webhook",
    action_config={"url": "https://hooks.slack.com/..."},
)
```

"If any agent emits an alert, post to Slack." "If the backend agent goes silent for 2 hours, create a focus item." Triggers turn Vigil from a passive awareness layer into an active coordination system.

## MCP Server: The Distribution Play

Everything above is available as an MCP server:

```bash
vigil serve                          # stdio (Claude Code, Claude Desktop)
vigil serve --transport sse          # SSE (remote clients)
vigil serve --transport http         # REST API + dashboard
```

12 MCP tools: boot, compile, signal, status, signals, handoff, resume, chain, stale, focus, frames, agents.

Any MCP-compatible client (Claude Code, Cursor, Windsurf, Claude Desktop) connects and gets persistent awareness. The agent boots with context, emits signals during work, and hands off when done. Next session picks up where it left off.

## The Numbers

| Metric | Value |
|--------|-------|
| Modules | 14 |
| Lines of code | 7,100+ |
| Tests | 252 |
| MCP tools | 12 |
| REST endpoints | 20 |
| Dashboard pages | 5 |
| Dependencies | 0 (stdlib only, MCP is optional) |
| Infrastructure | SQLite (zero setup) |

## Why Not [Existing Tool]?

| | Vigil | Mem0 | Letta | LangGraph |
|---|---|---|---|---|
| **Approach** | Awareness daemon | Memory retrieval | Stateful runtime | State machine |
| **Context** | Pre-compiled, instant | Query on demand | LLM-managed | Checkpoint-based |
| **Tool filtering** | Frame-based (75-85% savings) | None | None | None |
| **Multi-agent** | Signal protocol + handoff | Shared memory | Single agent | Graph edges |
| **Compaction** | Tiered retention | None | LLM-managed | None |
| **MCP native** | Built-in server | No | No | No |
| **Infrastructure** | SQLite | API + LLM costs | Full runtime | LangChain ecosystem |

These aren't competitors — they're complementary. Vigil handles awareness and coordination. Mem0 handles deep memory. Use both.

## Get Started

```bash
pip install vigil-agent

vigil init
vigil signal my-agent "Starting work on the auth system"
vigil daemon start
vigil status
```

Or as an MCP server:

```bash
pip install "vigil-agent[mcp]"
vigil serve
```

252 tests. MIT license. Zero external dependencies.

**GitHub:** [github.com/AlexlaGuardia/Vigil](https://github.com/AlexlaGuardia/Vigil)
**PyPI:** [pypi.org/project/vigil-agent](https://pypi.org/project/vigil-agent/)

---

*This is v1.5.0. The roadmap includes a hosted multi-tenant platform, federation protocol for cross-org agent coordination, and eventually a hardware device (Pi-based always-on awareness hub). If you're building multi-agent systems and fighting the same problems, I'd love to hear how you're solving them.*
