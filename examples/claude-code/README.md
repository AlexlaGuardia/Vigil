# Vigil + Claude Code

Wire Vigil into Claude Code so every session boots with awareness and emits signals automatically.

## 1. Add Vigil as MCP Server

```bash
claude mcp add vigil -- vigil serve
```

Or manually in your MCP config:

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

## 2. Add to CLAUDE.md

Add this to your project's `CLAUDE.md` so Claude Code uses Vigil automatically:

```markdown
## Vigil Integration

This project uses Vigil for cross-session awareness. At the start of every session:

1. Call `vigil_boot` to load context from the last session
2. Check the handoff chain for pending next steps

During work:
- Call `vigil_signal` after significant changes (deploys, refactors, bug fixes)
- Keep signals concise (under 400 chars for observations)

At session end:
- Call `vigil_handoff` with a summary, files touched, and next steps
```

## 3. Add Session Hooks (Optional)

Create `.claude/hooks/session-start.sh`:

```bash
#!/bin/bash
# Auto-emit a start signal when Claude Code opens
vigil signal claude-code "Session started in $(basename $(pwd))" --type observation
```

Create `.claude/hooks/session-end.sh`:

```bash
#!/bin/bash
# Auto-signal session end (handoff should already be done by Claude)
vigil signal claude-code "Session ended" --type observation
```

Make them executable:

```bash
chmod +x .claude/hooks/session-start.sh .claude/hooks/session-end.sh
```

## What You Get

- Every Claude Code session boots with awareness of what happened before
- Signals from your work are captured and compiled by the daemon
- Next session picks up exactly where you left off via handoff chain
- Multiple Claude Code windows coordinate through the signal bus
