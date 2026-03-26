# Vigil + Claude Desktop

Add Vigil as an MCP server in Claude Desktop for persistent awareness across conversations.

## Setup

Add to your Claude Desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "vigil": {
      "command": "vigil",
      "args": ["serve"],
      "env": {
        "VIGIL_DB": "/path/to/your/project/vigil.db"
      }
    }
  }
}
```

> Set `VIGIL_DB` to the path of your project's Vigil database. If omitted, it defaults to `vigil.db` in the working directory.

## Available Tools in Claude Desktop

Once connected, Claude Desktop has access to 12 Vigil tools:

| Tool | What It Does |
|------|-------------|
| `vigil_boot` | Load awareness context at conversation start |
| `vigil_signal` | Emit a signal (log what you're doing) |
| `vigil_status` | Check current system awareness |
| `vigil_handoff` | End session with structured summary |
| `vigil_resume` | Resume from last agent's handoff |
| `vigil_focus` | View/manage the priority work queue |
| `vigil_frames` | List available context frames |
| `vigil_agents` | See all known agents and their activity |
| `vigil_signals` | Read recent signals |
| `vigil_chain` | View handoff chain (last N sessions) |
| `vigil_stale` | Find agents that have gone silent |
| `vigil_compile` | Force a fresh awareness compilation |

## Usage Pattern

Start each conversation with:
> "Boot Vigil and tell me what's going on."

Claude will call `vigil_boot` and give you a summary of the current state, recent signals, and any pending work from the last session.

End each conversation with:
> "Hand off — summarize what we did and what's next."

Claude will call `vigil_handoff` with a structured summary for the next session.
