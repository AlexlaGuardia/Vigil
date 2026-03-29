# Vigil

**Cognitive infrastructure for AI agents.**

Vigil gives your AI agents a nervous system — awareness of what's happening, memory of what happened, and the ability to coordinate without talking directly to each other.

Most agent memory tools are filing cabinets. Vigil is a nervous system.

## The Problem

AI agents forget everything between sessions. They load all tools regardless of context (wasting 50K+ tokens). They can't coordinate across sessions or hand off work to each other. Every conversation starts cold.

## What Vigil Does

**Awareness Daemon** — A background process compiles system state every 90 seconds. Agents boot with pre-compiled context in <1 second. No startup latency, no "remind me what we were doing."

**Frame-Based Tool Filtering** — Tag tools with context frames. An agent in "backend" mode sees 14 tools, not 95. Saves 50-90% of tool-definition tokens per session.

**Signal Protocol** — Lightweight event bus with content budgets. Agents emit signals (max 300-800 chars by type), the daemon synthesizes them into awareness. Agents coordinate without direct communication.

**Session Handoff** — Agents end sessions with structured summaries (files touched, decisions, next steps). The next agent boots with full context of what happened and what to do next.

**Signal Compaction** — Old signals get summarized, not deleted. Tiered retention (raw → daily → weekly → monthly) keeps context fresh without losing history.

**MCP Server** — Expose Vigil as an MCP tool server. Any Claude Code, Claude Desktop, Cursor, or Windsurf agent connects and gets persistent awareness instantly.

## Install

```bash
# Core library (daemon, signals, handoff, compaction)
pip install vigil-agent

# With MCP server support
pip install vigil-agent[mcp]
```

## 30-Second Demo

See Vigil work in four commands:

```bash
pip install vigil-agent
vigil init
vigil signal my-agent "Hello from Vigil!"
vigil status
```

Expected output:

```
Current Awareness
─────────────────
  Agents:  my-agent (1 signal)
  Latest:  "Hello from Vigil!" (just now)
  Frame:   default
  Status:  active — 1 unacknowledged signal
```

That's it — your agent has awareness. Read on for the full quickstart with daemon, handoff, and MCP server.

## Quickstart

```bash
# Initialize
vigil init

# Emit a signal
vigil signal my-agent "Deployed new API endpoint"

# Start the daemon (compiles awareness every 90s)
vigil daemon start

# Check awareness
vigil status

# See what agents boot with
vigil boot --json

# End a session with a structured handoff
vigil handoff my-agent "Shipped auth module" --files "auth.py, tests.py" --next-steps "Write docs"

# Resume from where the last agent left off
vigil resume next-agent

# Start as an MCP server (Claude Code / Claude Desktop)
vigil serve

# Run signal compaction manually
vigil compact --dry-run
```

## MCP Server

Vigil runs as an MCP server so any AI agent can connect and get persistent awareness.

```bash
# stdio (Claude Code, Claude Desktop)
vigil serve

# SSE (remote clients)
vigil serve --transport sse --port 8300
```

**Claude Desktop config** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "vigil": {
      "command": "vigil",
      "args": ["serve"]
    }
  }
}
```

**12 MCP tools available:**

| Tool | Description |
|------|-------------|
| `vigil_boot` | Boot with pre-compiled hot context |
| `vigil_compile` | Force a fresh awareness compilation |
| `vigil_signal` | Emit a signal from an agent |
| `vigil_status` | Get current awareness state |
| `vigil_signals` | Read recent signals |
| `vigil_handoff` | End session with structured handoff |
| `vigil_resume` | Resume from last handoff |
| `vigil_chain` | Get briefing of last N handoffs |
| `vigil_stale` | Find agents that have gone silent |
| `vigil_focus` | Manage priority work queue |
| `vigil_frames` | Manage context frames |
| `vigil_agents` | List known agents and activity |

## Python API

```python
from vigil import VigilDB, SignalBus, AwarenessCompiler, HandoffProtocol

# Initialize
db = VigilDB("vigil.db")
bus = SignalBus(db)
compiler = AwarenessCompiler(db)
proto = HandoffProtocol(db)

# Emit signals from agents
bus.emit("backend-agent", "Deployed auth service v2")
bus.emit("frontend-agent", "Updated dashboard layout")

# Compile awareness
compiler.synthesize()
context = compiler.compile()
# {'frame': 'backend', 'awareness': '...', 'focus': [...], 'compiled_at': '...'}

# Boot an agent with pre-compiled context (<1 second)
hot_context = compiler.boot()

# Structured session handoff
proto.end_session(
    agent_id="backend-agent",
    summary="Shipped auth v2 with JWT tokens",
    files_touched=["auth.py", "middleware.py"],
    decisions=["Switched from session cookies to JWT"],
    next_steps=["Add rate limiting", "Write integration tests"],
)

# Next agent resumes with full context
context = proto.resume("next-agent")
# {'awareness': ..., 'last_handoff': {...}, 'signals_since_handoff': [...], 'pending_next_steps': [...]}
```

### Frame-Based Tool Filtering

```python
from vigil.registry import tool, get_tools, tool_count

# Tag tools with frames
@tool(name="deploy", description="Deploy to production", frames=["backend", "devops"])
async def deploy(args):
    return {"content": [{"type": "text", "text": f"Deployed {args['service']}"}]}

@tool(name="render", description="Render component", frames=["frontend"])
async def render(args):
    ...

@tool(name="health", description="Health check", frames=["core"])  # Always visible
async def health(args):
    ...

# Filter by context
tool_count()              # 3 (all tools)
tool_count("backend")     # 2 (deploy + health)
tool_count("frontend")    # 2 (render + health)
```

### Signal Compaction

```python
from vigil import SignalCompactor

compactor = SignalCompactor(db)

# Run compaction (tiered: raw → daily → weekly → monthly)
stats = compactor.compact()
# {'daily_summaries': 5, 'weekly_digests': 2, 'monthly_snapshots': 1, 'signals_compacted': 47}

# Browse compacted history
history = compactor.get_history(days=30, agent="backend-agent")
```

### Signal Types & Budgets

| Type | Budget | Use |
|------|--------|-----|
| `observation` | 400 chars | Regular activity updates |
| `handoff` | 600 chars | Session conclusions |
| `summary` | 800 chars | Comprehensive summaries |
| `alert` | 300 chars | Urgent notifications |

## Architecture

```
Agents emit signals → SQLite → Daemon compiles → Hot context → Agents boot instantly
                                    ↓
                            Frame detection
                            Awareness synthesis
                            Signal compaction
                            Focus queue
```

- **Zero infrastructure** — SQLite storage, no Redis/Postgres/Docker required
- **Framework-agnostic** — Works with any MCP-compatible client, or standalone
- **Lightweight** — Pure Python, no heavy dependencies (mcp is optional)

## Integrations

Ready-to-use configs for popular AI tools. See the [`examples/`](examples/) directory for full setup guides.

| Tool | Setup |
|------|-------|
| **Claude Code** | `claude mcp add vigil -- vigil serve` ([guide](examples/claude-code/)) |
| **Claude Desktop** | Add to `claude_desktop_config.json` ([guide](examples/claude-desktop/)) |
| **Cursor** | Add to `.cursor/mcp.json` ([guide](examples/cursor/)) |
| **GitHub Actions** | Emit signals from CI/CD ([workflow](examples/github-actions/)) |
| **Slack** | Route alerts to Slack via triggers ([guide](examples/slack-webhook/)) |
| **Discord** | Route alerts to Discord via triggers ([guide](examples/discord-webhook/)) |

### Shell Completion

```bash
# Bash
source completions/vigil.bash

# Zsh
cp completions/vigil.zsh ~/.zsh/completions/_vigil
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `vigil init` | Initialize a new project |
| `vigil quickstart` | Interactive setup wizard |
| `vigil daemon start` | Start the awareness daemon |
| `vigil daemon status` | Check daemon compilation status |
| `vigil serve` | Start as MCP server (stdio or SSE) |
| `vigil signal <agent> <msg>` | Emit a signal |
| `vigil status` | Show current awareness |
| `vigil boot` | Show compiled hot context |
| `vigil frames` | List registered frames |
| `vigil tools [--frame X]` | List tools (optionally filtered) |
| `vigil handoff <agent> <summary>` | Write a structured session handoff |
| `vigil resume <agent>` | Resume from last handoff |
| `vigil history` | Browse compacted signal history |
| `vigil agents` | List known agents |
| `vigil compact` | Run signal compaction manually |
| `vigil know <key> <value>` | Store a knowledge entry |
| `vigil recall <query>` | Fuzzy-search knowledge |
| `vigil knowledge` | List all knowledge entries |
| `vigil forget <key>` | Delete a knowledge entry |
| `vigil extract` | Auto-extract knowledge from signal patterns |
| `vigil export` | Export state to markdown |
| `vigil mcp-health` | MCP server health (calls, errors, latency) |
| `vigil mcp-health-check <cmd>` | Probe MCP server in CI (exit 0/1) |
| `vigil doctor` | Diagnose common issues |
| `vigil version` | Show version |

## MCP Production Observability

Monitor any MCP server with one line of code. Tracks tool calls, latency, errors, and emits alerts automatically.

```python
from mcp.server.fastmcp import FastMCP
from vigil.mcpwatch import instrument

mcp = FastMCP("my-server")

@mcp.tool()
async def search(query: str) -> str:
    return "results"

# One line — all tools are now monitored
watch = instrument(mcp)
```

**What it monitors:**
- Every tool call: name, duration, success/error
- Latency spikes (configurable threshold, default 5s)
- Error patterns with full tracebacks
- Silent failures (no calls for N minutes)

**Three ways to use it:**

```python
# 1. Local Vigil — store in same DB as your signals
watch = instrument(mcp, db_path="vigil.db")

# 2. Vigil Cloud — send to your hosted instance
watch = instrument(mcp, api_key="vgl_...")

# 3. Memory-only — just in-process stats
watch = instrument(mcp)
```

**Check health anytime:**
```python
health = watch.health()
# {'server': 'my-server', 'status': 'healthy', 'total_calls': 1247,
#  'error_rate': 0.02, 'tools': {'search': {'avg_ms': 42, 'p95_ms': 180}}}
```

**CLI:**
```bash
vigil mcp-health              # All monitored servers
vigil mcp-health -s my-server # Specific server
```

**REST API (5 endpoints):**
| Endpoint | Description |
|----------|-------------|
| `GET /mcp/health` | Server health summary |
| `GET /mcp/tools` | Per-tool analytics |
| `GET /mcp/errors` | Recent errors |
| `GET /mcp/latency` | p50/p95/p99 percentiles |
| `GET /mcp/volume` | Call volume over time |

## Why Not Just Use Mem0/Letta/LangGraph?

| | Vigil | Mem0 | Letta | LangGraph |
|---|---|---|---|---|
| **Approach** | Awareness daemon | Memory retrieval | Stateful runtime | State machine |
| **Context** | Pre-compiled, instant boot | Query on demand | LLM-managed | Checkpoint-based |
| **Tool filtering** | Frame-based (50-90% savings) | None | None | None |
| **Multi-agent** | Signal protocol + handoff | Shared memory | Single agent | Graph edges |
| **Compaction** | Tiered (daily/weekly/monthly) | None | LLM-managed | None |
| **MCP native** | Built-in server | No | No | No |
| **Infrastructure** | SQLite (zero setup) | API + LLM costs | Full runtime | LangChain ecosystem |
| **Lock-in** | None (framework-agnostic) | Mem0 API | Letta platform | LangChain |

Vigil is the nervous system. Others are the filing cabinet. Use them together — Vigil handles awareness and coordination, Mem0/Letta handles deep memory.

## License

MIT
