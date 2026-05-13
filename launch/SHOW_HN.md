# Show HN Submission

**Title:** Show HN: Vigil -- Cognitive infrastructure for AI agents (awareness daemon, MCPWatch, session handoff)

**URL:** https://github.com/AlexlaGuardia/Vigil

**Text:**

I've been building AI agent systems for the past year and kept running into three problems:

1. Agents forget everything between sessions. Every conversation starts cold.
2. Loading all tools into context wastes 50K+ tokens before the agent does anything useful.
3. Multiple agents can't coordinate without being in the same process.

Vigil is my answer. It's a Python library that gives agents a nervous system instead of just a filing cabinet:

- **Awareness daemon** runs in the background, compiling system state every 90 seconds into "hot context." Agents boot with full awareness in <1 second.

- **Frame-based tool filtering** lets you tag tools with context modes. An agent in "backend" mode sees 14 tools, not 95. Saves 75-85% of tool-definition tokens.

- **Signal protocol** is a lightweight event bus where agents emit short messages (300-800 chars with content budgets). The daemon synthesizes these into awareness. Agents coordinate without talking to each other directly.

- **Session handoff** — agents end sessions with structured summaries (files touched, decisions, blockers, next steps). The next agent resumes with full context. Handoff chains track continuity across sessions.

- **Knowledge auto-extract** — the daemon watches signal patterns and automatically suggests persistent knowledge entries. Recurring phrases and agent behaviors get surfaced without manual tagging.

- **Event triggers** — pattern-match on signals and fire actions (webhooks, focus items, log entries). "If any agent emits an alert, notify Slack."

- **MCP server** — `vigil serve` exposes 12 tools over MCP (stdio or SSE). Claude Code, Cursor, Claude Desktop, Windsurf — any MCP client connects and gets persistent awareness instantly.

Storage is SQLite (zero infrastructure). Signal compaction keeps history manageable (tiered: raw → daily → weekly → monthly summaries). There's a built-in dashboard if you run `vigil serve --transport http`, and integration examples for Claude Code, Cursor, GitHub Actions, Slack, and Discord.

I built this because I was running ~95 MCP tools across multiple AI agents (coding, trading, creative writing) and the context window overhead was killing me. Frame filtering cut my token usage by 75-85%. Session handoff means I can close a session at 2am and pick up the next morning without losing anything.

v2.2.0 on PyPI: `pip install vigil-agent`. 14 modules, 311 tests, 8,400+ lines. MIT license. Zero dependencies beyond stdlib (MCP support is an optional extra). Tab completion for bash/zsh included.

New in v2.0+: MCPWatch (one-line MCP server observability with per-tool metrics, latency percentiles, error tracking, and CI health checks), WebSocket real-time signal streaming, audit logging, and rate-limited multi-tenant hosting.

Happy to answer questions about the architecture, the MCP ecosystem, or how I'm using this in production.

Deeper dive on MCPWatch specifically: https://dev.to/alexlaguardia/your-mcp-servers-are-flying-blind-heres-how-to-fix-it-3g51
