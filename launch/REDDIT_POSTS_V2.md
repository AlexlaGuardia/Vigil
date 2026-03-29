# Reddit Posts — Vigil v2.2 (human draft)

## r/ClaudeAI

**Title:** I got tired of typing "remind me what we were working on" every session

Every time I open Claude Code, the first thing I do is explain what happened in the last session. What files I touched, what decisions I made, what's left to do. Every. Single. Time.

I run about 95 MCP tools across a few projects. Backend work, trading system, creative writing. The agent loads all 95 tool definitions every session even though I usually need 14-20 of them. That's ~50K tokens gone before anything useful happens.

I finally snapped and wrote a background daemon that watches what my agents do and compiles a state file every 90 seconds. New session opens, agent reads the file, and it just picks up where things left off. No re-explaining, no "let me re-read all 47 files."

The other piece that helped more than I expected: frame-based tool filtering. I tag tools with contexts — "backend", "frontend", "creative" — and the agent only sees what's relevant. Backend mode shows 14 tools instead of 95. Token usage dropped noticeably.

It's a Python package called Vigil. Works as an MCP server so it plugs into Claude Code, Claude Desktop, or Cursor with one line:

```
claude mcp add vigil -- vigil serve
```

Now Claude gets tools like `vigil_boot` (loads context from previous sessions), `vigil_signal` (logs what the agent is doing), and `vigil_handoff` (structured session end so the next session knows what to do).

It's not trying to be Mem0 or Letta — those handle long-term memory. This is more like... awareness. What's happening right now across your agents.

MIT license, zero dependencies, on PyPI: `pip install vigil-agent`

GitHub: https://github.com/AlexlaGuardia/Vigil

---

## r/LocalLLaMA

**Title:** Built a background daemon that gives agents persistent context between sessions

I run a mix of Claude Code and local models across different projects and kept running into the same problem: every session starts from absolute zero. The agent has no idea what happened 5 minutes ago in a different window.

My janky solution for months was a markdown file I'd manually update with "here's what happened." That obviously doesn't scale when you're running multiple agents.

So I wrote a daemon that does it automatically. It watches signals that agents emit (short messages about what they're doing), compiles them into a single awareness state every 90 seconds, and stores it in SQLite. When a new session starts, the agent reads the compiled state and boots with full context in under a second.

The part that surprised me: frame-based tool filtering ended up being just as useful. I have ~95 MCP tools registered. Tagging them with frames ("backend", "frontend", etc.) means the agent only sees what's relevant to the current task. Went from 95 tool definitions in context to 14-20. Real token savings if you're running local models where context matters even more.

Other stuff it does:
- Session handoff: structured summary of files touched, decisions, next steps. Next agent picks up clean.
- Event triggers: pattern-match on signals, fire webhooks. "If deploy agent says error, ping Slack."
- Signal compaction: old signals get compressed into daily/weekly/monthly summaries so the DB doesn't grow forever.
- Works as an MCP server (stdio or SSE) — plugs into Claude Code, Cursor, Claude Desktop, whatever.

It's called Vigil. Python, MIT, zero external deps, SQLite storage.

```
pip install vigil-agent
vigil init
vigil daemon start
vigil serve  # MCP server mode
```

Not a memory layer (Mem0/Letta/Zep handle that). This is the coordination layer — what's happening now, not what you said three weeks ago. Complementary, not competing.

GitHub: https://github.com/AlexlaGuardia/Vigil

There's also a hosted cloud tier at https://vigil-agent.com if you don't want to self-host (free tier available).
