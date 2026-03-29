# Reddit Posts — Vigil v2.2

## r/LocalLLaMA

**Title:** I built a "nervous system" for AI agents — awareness daemon, MCP observability, session handoff, hosted cloud tier (Python, MIT)

**Body:**

I've been running multiple AI agents (Claude Code, local LLMs via Ollama, etc.) across different projects and kept hitting the same problems:

1. Every session starts cold — agents have no idea what happened 5 minutes ago in a different session
2. Loading 95 tool definitions burns ~50K tokens before anything useful happens
3. Multiple agents can't hand off work to each other
4. MCP servers fail silently in production — no monitoring, no alerts

So I built Vigil — a Python library that adds a coordination layer:

**Core features:**
- **Awareness daemon** compiles system state every 90s. Agents boot with full context in <1 second.
- **Frame-based tool filtering** — tag tools with context modes. "Backend" mode shows 14 tools, not 95. 75-85% token savings.
- **Signal protocol** — lightweight event bus. Agents emit signals, daemon synthesizes into awareness.
- **Session handoff** — structured summaries: files touched, decisions, next steps. Next agent picks up where you left off.
- **MCP Production Observability (MCPWatch)** — one-line `instrument(server)` wraps any MCP server. Tracks tool calls, latency (p50/p95/p99), error rates, silent failures. Alerts when things go wrong.
- **Event triggers** — pattern-match signals → fire webhooks, Slack alerts, etc.
- **MCP server** — works with Claude Code, Cursor, Claude Desktop, or any MCP client.

**Hosted cloud tier (app.vigil-agent.com):**
- GitHub OAuth → dashboard → API keys → connect agents
- Free tier: 5K signals/mo, 2 agents
- WebSocket real-time signal stream, signal analytics, audit log
- Pro/Team/Enterprise tiers coming Q3 2026

**What it's NOT:**
- Not a memory store (Mem0/Letta handle that — Vigil is complementary)
- Not an orchestration framework (LangGraph handles that)
- Not tied to any specific LLM or provider

**The numbers:** 14 modules, 311 tests, 8,400+ lines, SQLite storage, zero external dependencies. MIT license.

```bash
pip install vigil-agent
vigil init
vigil signal my-agent "Hello from Vigil!"
vigil status
```

Integration examples for Claude Code, Cursor, Claude Desktop, GitHub Actions, Slack, and Discord.

GitHub: https://github.com/AlexlaGuardia/Vigil
Landing page: https://vigil-agent.com

Happy to answer questions. I've been running this in production for months — it coordinates a coding agent, a trading system, and a creative writing setup across the same server.

---

## r/ClaudeAI

**Title:** I built a persistent awareness layer for Claude Code / Claude Desktop — session handoff, MCP monitoring, tool filtering

**Body:**

If you use Claude Code or Claude Desktop with MCP tools, you've probably noticed: every session starts from scratch. The agent has no idea what happened in your last conversation. If you're running 50+ tools, you're burning tokens loading tool definitions the agent won't use. And if an MCP server fails silently? Nobody knows until you notice tools aren't working.

I built Vigil to fix this. It's a Python library + MCP server that gives Claude persistent awareness:

**Setup with Claude Code:**

```bash
pip install vigil-agent
vigil init
claude mcp add vigil -- vigil serve
```

Now Claude has 12 new tools:
- `vigil_boot` — loads awareness context from previous sessions
- `vigil_signal` — logs what Claude is doing (for the next session to see)
- `vigil_handoff` — structured session end (files touched, decisions, next steps)
- `vigil_resume` — picks up where the last session left off

**The features that matter:**

- **Frame-based tool filtering**: Tag your tools with frames ("backend", "frontend", etc.). Claude in "backend" mode only sees relevant tools. I went from 95 tools to 14-25 per session — 75-85% fewer tool definitions in context.

- **Session handoff chains**: Close Claude Code at 2am, open it next morning. Claude boots with full context of what happened and what to do next.

- **Signal protocol**: Multiple Claude Code windows? They coordinate through the signal bus without direct communication.

- **MCPWatch (new in v2.0)**: One-line instrumentation for any MCP server. Tracks tool call latency (p50/p95/p99), error rates, silent failures. Alerts when your MCP servers degrade.

- **Hosted cloud tier**: Sign up at app.vigil-agent.com (GitHub OAuth). Free tier: 5K signals/mo. Dashboard with real-time signal stream, analytics, API key management.

v2.2.0 on PyPI. 311 tests, MIT license, zero dependencies (MCP is optional extra).

GitHub: https://github.com/AlexlaGuardia/Vigil
Cloud: https://app.vigil-agent.com
Dev.to: https://dev.to/alexlaguardia/i-built-a-nervous-system-for-ai-agents-not-another-memory-store-5a8a
