# Show HN Submission

**Title:** Show HN: Vigil – Awareness daemon and frame-based tool filtering for AI agents

**URL:** https://github.com/AlexlaGuardia/Vigil

**Text:**

I've been building AI agent systems for the past year and kept running into three problems:

1. Agents forget everything between sessions. Every conversation starts cold.
2. Loading all tools into context wastes 50K+ tokens before the agent does anything useful.
3. Multiple agents can't coordinate without being in the same process.

Vigil is my answer. It's a Python library that gives agents a nervous system instead of just a filing cabinet:

- **Awareness daemon** runs in the background, compiling system state every 90 seconds into "hot context." Agents boot with full awareness in <1 second. No startup latency.

- **Frame-based tool filtering** lets you tag tools with context modes. An agent in "backend" mode sees 14 tools, not 95. Saves 50-90% of tool-definition tokens.

- **Signal protocol** is a lightweight event bus where agents emit short messages (300-800 chars with content budgets). The daemon synthesizes these into awareness. Agents coordinate without talking to each other directly.

Storage is SQLite (zero infrastructure). Works with any MCP-compatible client or standalone. `pip install vigil-agent` and you're running.

I built this because I was running ~95 MCP tools across multiple AI agents (coding, trading, creative writing) and the context window overhead was killing me. The frame filtering alone cut my token costs dramatically. The daemon means I can close a session at 2am and pick up the next morning with full context.

Happy to answer questions about the architecture or the MCP ecosystem in general.
