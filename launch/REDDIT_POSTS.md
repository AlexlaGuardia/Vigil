# Reddit Posts — Vigil v1.5.1

## r/LocalLLaMA

**Title:** I built a "nervous system" for AI agents — awareness daemon, frame-based tool filtering, session handoff (Python, framework-agnostic)

**Body:**

I've been running multiple AI agents (Claude Code, local LLMs via Ollama, etc.) across different projects and kept hitting the same problems:

1. Every session starts cold — agents have no idea what happened 5 minutes ago in a different session
2. Loading 95 tool definitions burns ~50K tokens before anything useful happens
3. Multiple agents can't hand off work to each other

So I built Vigil — a Python library that adds a coordination layer:

**What it does:**
- **Awareness daemon** compiles system state every 90s. Agents boot with full context in <1 second.
- **Frame-based tool filtering** — tag tools with context modes. "Backend" mode shows 14 tools, not 95. 75-85% token savings.
- **Signal protocol** — lightweight event bus (300-800 char messages). Agents emit signals, daemon synthesizes into awareness.
- **Session handoff** — structured summaries: files touched, decisions, next steps. Next agent picks up where you left off.
- **Knowledge auto-extract** — daemon watches signal patterns and surfaces recurring themes as persistent knowledge.
- **Event triggers** — pattern-match signals → fire webhooks, Slack alerts, etc.
- **MCP server** — works with Claude Code, Cursor, Claude Desktop, or any MCP client.

**What it's NOT:**
- Not a memory store (Mem0/Letta handle that — Vigil is complementary)
- Not an orchestration framework (LangGraph handles that)
- Not tied to any specific LLM or provider

**The numbers:** 14 modules, 268 tests, 7,500+ lines, SQLite storage, zero external dependencies. MIT license.

```bash
pip install vigil-agent
vigil init
vigil daemon start
vigil serve  # MCP server mode
```

Integration examples included for Claude Code, Cursor, GitHub Actions, Slack, and Discord.

GitHub: https://github.com/AlexlaGuardia/Vigil

Happy to answer questions. I've been running this in production for months — it coordinates a coding agent, a trading system, and a creative writing setup across the same server.

---

## r/ClaudeAI

**Title:** I built a persistent awareness layer for Claude Code / Claude Desktop — session handoff, tool filtering, signal coordination

**Body:**

If you use Claude Code or Claude Desktop with MCP tools, you've probably noticed: every session starts from scratch. The agent has no idea what happened in your last conversation. If you're running 50+ tools, you're burning tokens loading tool definitions the agent won't use.

I built Vigil to fix this. It's a Python library + MCP server that gives Claude persistent awareness:

**How it works with Claude:**

1. `pip install vigil-agent && vigil init`
2. Add to Claude Code: `claude mcp add vigil -- vigil serve`
3. Or Claude Desktop config: `{"mcpServers": {"vigil": {"command": "vigil", "args": ["serve"]}}}`

Now Claude has 12 new tools:
- `vigil_boot` — loads awareness context from previous sessions
- `vigil_signal` — logs what Claude is doing (for the next session to see)
- `vigil_handoff` — structured session end (files touched, decisions, next steps)
- `vigil_resume` — picks up where the last session left off

**The killer features:**

- **Frame-based tool filtering**: Tag your tools with frames ("backend", "frontend", etc.). Claude in "backend" mode only sees relevant tools. I went from 95 tools to 14-25 per session — 75-85% fewer tool definitions in context.

- **Session handoff chains**: Close Claude Code at 2am, open it next morning. Claude boots with full context of what happened and what to do next.

- **Signal protocol**: Multiple Claude Code windows? They coordinate through the signal bus without direct communication. One window deploys, the other sees it in its awareness.

- **Knowledge auto-extract**: The daemon watches signal patterns and automatically builds persistent knowledge. Recurring activities get surfaced.

v1.5.1 on PyPI. 268 tests, MIT license, zero dependencies (MCP is optional extra).

Ready-to-use examples for Claude Code, Claude Desktop, Cursor, GitHub Actions, Slack, and Discord.

GitHub: https://github.com/AlexlaGuardia/Vigil

Also wrote a technical deep-dive: https://dev.to/alexlaguardia/i-built-a-nervous-system-for-ai-agents-not-another-memory-store-5a8a
