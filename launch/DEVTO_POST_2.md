---
title: "How I Built a Full Product in One Night with 3 Parallel AI Agents"
published: false
description: "From a 1,200-line library to a 5,900-line product with MCP server, REST API, dashboard, and event triggers — in a single session using 3 Claude Code windows."
tags: ai, productivity, python, opensource
cover_image: https://raw.githubusercontent.com/AlexlaGuardia/Vigil/main/cover.png
---

Last Thursday night I sat down to add session handoff to my Python library. I stood up 8 hours later with a complete product: MCP server, REST API, embedded dashboard, event triggers, signal compaction. From 1,200 lines to 5,900. From a CLI tool to something with a web UI.

Here's how, and why the technique matters more than the project.

## The Setup

I'd built [Vigil](https://github.com/AlexlaGuardia/Vigil) — an awareness daemon for AI agents. It worked great as a CLI tool: emit signals, compile state, boot agents with context. But it was missing the features that make it a real product: session handoff, an MCP server for Claude/Cursor integration, a REST API, and a dashboard.

Each of these features lives in its own module. They share the database layer but have no code dependencies on each other. That's the key insight.

## The Technique: Parallel AI Windows

I opened three Claude Code terminal windows, each working on a separate file:

- **Window 1:** Session handoff protocol (`handoff.py`)
- **Window 2:** Signal compaction engine (`compaction.py`)
- **Window 3:** MCP server mode (`mcp_server.py`)

Each window had the same context: the existing codebase, the database schema, the module interfaces. But they worked independently, writing to separate files. No merge conflicts.

While those three were building, I reviewed their output periodically and planned the next batch. When all three finished, I opened a single integration window that wired everything together: imports, CLI commands, shared database migrations.

Then I repeated the pattern:

- **Window 1:** REST API (`api.py`)
- **Window 2:** Dashboard templates (5 HTML pages)
- **Window 3:** Event triggers (`triggers.py`)

Same idea. Independent files, parallel execution, single integration pass.

## What Made It Work

**1. Clean module boundaries.** Every feature was a new file that imported from existing modules (`db.py`, `signals.py`, `awareness.py`). No feature needed to modify another feature's code. This isn't accidental — I designed the architecture knowing I'd build this way.

**2. Stable interfaces.** The database schema and the `VigilDB` API were stable. All three windows could `from vigil.db import VigilDB` and trust that the interface wouldn't change under them.

**3. Integration is the bottleneck, not implementation.** Each module took 30-60 minutes to build. Integration — wiring CLI commands, updating `__init__.py`, running the test suite — took 20 minutes per batch. The integration step is where I caught type mismatches, missing imports, and interface disagreements.

**4. Mid-session code audit.** After the first batch (handoff + compaction + MCP), I ran a full code audit before starting batch two. Found 3 critical issues and 6 important ones. Fixing them before building the REST API prevented those bugs from propagating.

## The Numbers

| Metric | Before (v0.1) | After (v1.0) | Delta |
|--------|---------------|--------------|-------|
| Lines of code | 1,278 | 5,922 | +4,644 |
| Modules | 7 | 13 | +6 |
| Tests | 48 | 196 | +148 |
| CLI commands | 7 | 14 | +7 |

14 commits over 8 hours. Zero merge conflicts.

## What I'd Do Differently

**Start with the integration test, not the unit tests.** Each window wrote unit tests for its module. But the integration tests — "emit a signal, compile awareness, check the dashboard shows it" — came last. If I'd written those first, I'd have caught interface mismatches earlier.

**Define the REST API schema before building the dashboard.** Window 2 (dashboard) had to guess what the API response shapes would be, because Window 1 (API) was still being built. A shared types file or API schema would have eliminated that friction.

## Why This Matters Beyond My Project

The parallel AI window technique works for any codebase with clean module boundaries:

- **Microservices:** Each window builds a different service
- **Frontend components:** Each window builds a different page/component
- **Data pipelines:** Each window builds a different stage

The constraint is the same: modules must be independently buildable with stable interfaces between them. If feature B needs to call feature A's code and that code doesn't exist yet, you can't parallelize them.

This is also a strong argument for writing clean interfaces first. The 30 minutes I spent designing `VigilDB`'s API saved hours of integration pain later.

## The Product

Vigil v1.5.0 is on PyPI. It gives AI agents persistent awareness across sessions:

- **Awareness daemon** compiles system state every 90 seconds
- **Frame-based tool filtering** reduces context by 75-85%
- **Signal protocol** lets agents coordinate without direct communication
- **Session handoff** with structured summaries and resume
- **MCP server** with 12 tools (Claude Code, Cursor, Claude Desktop)
- **REST API** with 20 endpoints and SSE event stream
- **Dashboard** with live updates

```bash
pip install vigil-agent
vigil init
vigil daemon start
```

**GitHub:** [github.com/AlexlaGuardia/Vigil](https://github.com/AlexlaGuardia/Vigil)

---

*If you're building with AI coding assistants and want to move faster, try the parallel window technique on your next feature batch. The key is architecture that supports it — clean boundaries, stable interfaces, independent files.*
