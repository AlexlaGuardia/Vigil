# HN Comments — April 18, 2026
> Pick ONE to post today. Don't spray. Quality > volume.

## Option 1: "MCP as Observability Interface" (35 pts)
https://news.ycombinator.com/item?id=47778617

**BEST FIT** — This thread is directly about MCP + observability. MCPWatch exists for this.

**Comment:**

I've been running ~95 MCP tools across multiple projects and the observability gap is real. The kernel tracepoint approach is interesting but I think the bigger problem is simpler: most MCP servers have zero visibility into what tools are being called, how often they fail, or when latency degrades.

I built an observability layer for MCP servers that wraps any FastMCP server with one line of code. It tracks per-tool call counts, duration, error rates, p50/p95/p99 latency, and emits alerts when things go sideways. All in-memory with optional SQLite persistence.

The other angle nobody talks about: token cost. Loading 95 tool definitions into an LLM context burns ~50K tokens before the agent does anything. Frame-based filtering lets you scope which tools are visible based on what the agent is doing. My "backend" frame exposes 14 tools instead of 95. That alone cut my API costs significantly.

The prompt injection concern in this thread is valid. Narrowing the tool surface area per-context is a practical mitigation. An agent in a "read-only monitoring" frame literally cannot see mutation tools.

---

## Option 2: "What Claude Code's Source Revealed About AI Engineering Culture" (76 pts)
https://news.ycombinator.com/item?id=47772282

**Comment:**

The CLAUDE.md hierarchy pattern is underrated. I use the same approach across 6 projects: root CLAUDE.md loads for all sessions, per-project CLAUDE.md loads when you cd into that directory. It's a surprisingly effective way to give an agent domain-specific context without manual prompting.

What I found missing was the session handoff problem. Claude Code starts every session cold. If I close a terminal at 2am and pick up the next morning, all context is gone.

My solution was a background daemon that compiles system state every 90 seconds into a hot context file. When a new session opens, the agent reads one file and knows what was happening, what's blocked, and what changed since last time. Boot time went from "re-read 47 files" to under a second.

The other thing: tool definition bloat. The source shows Claude Code loads all available tools into context. With 95 MCP tools, that's a lot of tokens wasted on tools you won't use. Tagging tools with "frames" and filtering by context mode cut that by 75-85%.

---

## Posting Guidelines
- Post from HN account: Serberus
- NO links to Vigil in the comment. Let it be organic. If people ask, reply with the link.
- If someone engages, respond thoughtfully. That's where karma comes from.
- Don't post both on the same day. Space them 24h+.
