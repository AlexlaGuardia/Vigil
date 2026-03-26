# Vigil + Cursor

Add Vigil as an MCP server in Cursor for persistent project awareness.

## Setup

Create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "vigil": {
      "command": "vigil",
      "args": ["serve"],
      "env": {
        "VIGIL_DB": "vigil.db"
      }
    }
  }
}
```

## With SSE (Remote Server)

If your Vigil daemon runs on a remote server, use SSE transport:

```json
{
  "mcpServers": {
    "vigil": {
      "url": "http://your-server:8300/sse"
    }
  }
}
```

Start the server remotely:
```bash
vigil serve --transport sse --host 0.0.0.0 --port 8300
```

## Usage

Cursor's AI assistant will have access to all 12 Vigil MCP tools. Use them to:

1. **Boot with context** — `vigil_boot` at session start
2. **Log work** — `vigil_signal` after changes
3. **Hand off** — `vigil_handoff` when switching to another tool or ending work
4. **Resume** — `vigil_resume` to pick up where you or another agent left off

## Tip: Cursor Rules

Add to `.cursorrules` in your project:

```
When starting a coding session, call vigil_boot to load project awareness.
After significant changes, call vigil_signal to log what was done.
When ending a session, call vigil_handoff with files touched and next steps.
```
