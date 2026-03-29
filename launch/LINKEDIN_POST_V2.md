# LinkedIn Post — Vigil v2.2 (human draft)

"Remind me what we were working on."

I type that into Claude Code at least twice a day. Every session starts cold. The agent has no memory of what happened 20 minutes ago in a different window.

I got tired of being the memory layer between my own tools.

So I wrote a daemon that sits in the background, watches what my agents do, and compiles it into a single state file every 90 seconds. When a new session opens, the agent reads that file and just... knows.

No "let me re-read all 47 files." No burning 50K tokens loading tool definitions it won't use. It boots in under a second with full context.

The other thing that kept biting me: I run 95 MCP tools across different projects. But when I'm doing backend work, I need maybe 14 of those. Frame-based filtering lets me scope which tools are visible per context. My token bill dropped noticeably.

I called it Vigil. It's a Python package, MIT license, works with Claude Code, Cursor, Claude Desktop — anything that speaks MCP.

It's not a memory store (Mem0/Letta do that well). It's the layer above memory — what's happening right now, not what happened last week.

pip install vigil-agent

https://github.com/AlexlaGuardia/Vigil
