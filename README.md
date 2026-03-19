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

## Install

```bash
pip install vigil-agent
```

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
```

## Python API

```python
from vigil import VigilDB, SignalBus, FrameDetector, AwarenessCompiler

# Initialize
db = VigilDB("vigil.db")
bus = SignalBus(db)
compiler = AwarenessCompiler(db)

# Emit signals from agents
bus.emit("backend-agent", "Deployed auth service v2")
bus.emit("frontend-agent", "Updated dashboard layout")

# Compile awareness
compiler.synthesize()
context = compiler.compile()
# {'frame': 'backend', 'awareness': '...', 'focus': [...], 'compiled_at': '...'}

# Boot an agent with pre-compiled context (<1 second)
hot_context = compiler.boot()
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

### Daemon

```python
from vigil import VigilDaemon

# Run the awareness daemon
daemon = VigilDaemon(
    db_path="vigil.db",
    compile_interval=90,          # Seconds between compiles
    awareness_file="AWARENESS.md", # Optional: write markdown
    on_compile=lambda ctx: print(f"Compiled: {ctx['frame']}"),
)

# Blocking
daemon.run()

# Or background thread
daemon.start()
# ... do other work ...
daemon.stop()
```

### Signal Types & Budgets

| Type | Budget | Use |
|------|--------|-----|
| `observation` | 400 chars | Regular activity updates |
| `handoff` | 600 chars | Session conclusions |
| `summary` | 800 chars | Comprehensive summaries |
| `alert` | 300 chars | Urgent notifications |

```python
bus.emit("agent", "Working on auth", signal_type="observation")
bus.emit("agent", "Done for today. Next: finish tests.", signal_type="handoff")
bus.emit("monitor", "API latency spike!", signal_type="alert")
```

## Architecture

```
Agents emit signals → SQLite → Daemon compiles → Hot context → Agents boot instantly
                                    ↓
                            Frame detection
                            Awareness synthesis
                            Focus queue
```

- **Zero infrastructure** — SQLite storage, no Redis/Postgres/Docker required
- **Framework-agnostic** — Works with any MCP-compatible client, or standalone
- **Lightweight** — Pure Python, no heavy dependencies

## CLI Reference

| Command | Description |
|---------|-------------|
| `vigil init` | Initialize a new project |
| `vigil daemon start` | Start the awareness daemon |
| `vigil daemon status` | Check daemon compilation status |
| `vigil signal <agent> <msg>` | Emit a signal |
| `vigil status` | Show current awareness |
| `vigil boot` | Show compiled hot context |
| `vigil frames` | List registered frames |
| `vigil tools [--frame X]` | List tools (optionally filtered) |

## Why Not Just Use Mem0/Letta/LangGraph?

| | Vigil | Mem0 | Letta | LangGraph |
|---|---|---|---|---|
| **Approach** | Awareness daemon | Memory retrieval | Stateful runtime | State machine |
| **Context** | Pre-compiled, instant boot | Query on demand | LLM-managed | Checkpoint-based |
| **Tool filtering** | Frame-based (50-90% token savings) | None | None | None |
| **Multi-agent** | Signal protocol | Shared memory | Single agent | Graph edges |
| **Infrastructure** | SQLite (zero setup) | API calls + LLM costs | Full runtime replacement | LangChain ecosystem |
| **Lock-in** | None (framework-agnostic) | Mem0 API | Letta platform | LangChain |

Vigil is the nervous system. Others are the filing cabinet. Use them together if you want — Vigil handles awareness and coordination, Mem0/Letta handles deep memory.

## License

MIT
