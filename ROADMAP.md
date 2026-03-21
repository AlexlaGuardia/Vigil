# Vigil Roadmap
> Cognitive infrastructure for AI agents — awareness, not just memory.
> Last updated: 2026-03-21

## Strategic Position

Vigil is NOT a memory product. Mem0, Letta, Zep — they store facts. Vigil **coordinates awareness**. The play: become the standard awareness layer that sits above any memory system. Complementary, not competitive.

**Moat:** Daemon pattern + frame-based filtering + signal protocol with content budgets. Nobody else has this combination. The MCP ecosystem (97M monthly SDK downloads, 10K+ servers) is the distribution channel.

**Revenue path:** Open-source core → hosted tier ($19-49/mo) → hardware device (Phase 4).

---

## v0.1.0 — SHIPPED (2026-03-19)
> 1,278 lines, 7 modules, 48 tests

- [x] Awareness daemon (90s compile cycle)
- [x] Frame-based tool filtering (50-90% token savings)
- [x] Signal protocol (4 types, content budgets)
- [x] SQLite storage (zero infrastructure)
- [x] CLI: init, daemon, signal, status, frames, tools, boot
- [x] Tool registry with @tool() decorator
- [x] Focus queue (priority-ordered work items)
- [x] Session tracking (start/end with summary)
- [x] PyPI: `pip install vigil-agent`
- [x] GitHub: public, MIT license

---

## v0.5.0 — "The Protocol Release" (3-4 sessions)
> Goal: Make Vigil the missing coordination layer every MCP agent needs.

### Session Handoff Protocol (~1 session)
The killer feature nobody has. Agents write structured handoffs; next agent boots with full context.

- [ ] `HandoffProtocol` class: structured end-of-session output (what happened, files touched, decisions made, next steps)
- [ ] `vigil handoff <agent> --summary "..." --next "..."` CLI command
- [ ] Auto-handoff: daemon detects session end (no signals for N minutes) and compiles handoff from recent signals
- [ ] `vigil resume <agent>` — boot with last handoff context baked in
- [ ] Handoff chain: query what the last 3 agents did (compressed)

### Compaction Engine (~1 session)
Old signals get summarized, not just deleted. Context stays fresh without losing history.

- [ ] `SignalCompactor` class: group old signals by agent + timeframe, produce summaries
- [ ] Tiered retention: <24h = raw signals, 1-7d = daily summaries, 7-30d = weekly digests, 30d+ = monthly snapshots
- [ ] Compaction runs on maintenance cycle (configurable, default hourly)
- [ ] `vigil history [--days N]` — browse compacted signal history
- [ ] Summary table in DB: `compacted_signals (period, agent, summary, signal_count, created_at)`

### MCP Server Mode (~1-2 sessions)
THE distribution play. Any Claude/GPT/Gemini agent connects to Vigil as an MCP server.

- [ ] `vigil serve` — start Vigil as an MCP server (stdio + SSE transports)
- [ ] Expose core tools as MCP tools: `vigil_boot`, `vigil_signal`, `vigil_status`, `vigil_handoff`, `vigil_focus`
- [ ] Frame filtering works over MCP: `?frame=X` on SSE URL
- [ ] Works with Claude Code, Claude Desktop, Cursor, Windsurf, any MCP client
- [ ] Example config for claude_desktop_config.json in README
- [ ] Listed on mcp.so + Glama.ai + Smithery

### Agent Identity (~0.5 session)
Know who's talking to you.

- [ ] `agents` table: id, name, type, capabilities, last_seen, session_count
- [ ] `vigil register <agent-name> --type cli|mcp|api` — register an agent
- [ ] Auto-register on first signal if unknown agent
- [ ] `vigil agents` — list known agents with last activity
- [ ] Agent-scoped signal queries: "what did agent X do today?"

**v0.5 deliverables:** PyPI release, updated README with MCP server docs, Dev.to article ("Give Your AI Agents a Nervous System"), HN relaunch.

---

## v1.0.0 — "The Product Release" (5-8 sessions)
> Goal: Vigil as a standalone service. The thing you charge for.

### REST API (~2 sessions)
Vigil runs as a persistent HTTP service. Agents connect from anywhere.

- [ ] FastAPI wrapper: `/boot`, `/signal`, `/status`, `/handoff`, `/frames`, `/agents`
- [ ] API key auth (simple, per-project)
- [ ] `vigil serve --http --port 8300` alongside MCP mode
- [ ] Webhook support: POST to a URL when signals match patterns (e.g., alert signals → Slack)
- [ ] SSE stream: `/events` for real-time signal feed

### Knowledge Base (~1 session)
Persistent patterns and decisions agents can query. Not episodic memory — **institutional knowledge**.

- [ ] `knowledge` table: key, value, category, source_agent, confidence, created_at
- [ ] `vigil know <key> <value>` — store a pattern
- [ ] `vigil recall <query>` — fuzzy-match knowledge lookup
- [ ] Agents can store and query via MCP/REST
- [ ] Knowledge != signals. Signals are ephemeral events. Knowledge persists and accumulates.

### Dashboard (~2-3 sessions)
Web UI for observability. This is where the hosted tier lives.

- [ ] Single-page app (lightweight — htmx or vanilla JS, not React)
- [ ] Live view: active agents, signal stream, current frame, awareness state
- [ ] History view: signal timeline, handoff chain, compaction summaries
- [ ] Agent cards: per-agent activity, session count, last seen
- [ ] Frame map: which tools are in which frame, active frame highlighted
- [ ] Served by `vigil serve --dashboard`

### Event Triggers (~1 session)
Agents react to signals without polling.

- [ ] Pattern matching on signal content/type/agent
- [ ] Actions: emit signal, call webhook, update focus, change frame
- [ ] `vigil trigger add --on "alert from *" --do "webhook https://..."`
- [ ] Enables: CI agent emits "deploy failed" → Vigil triggers "rollback" signal to ops agent

**v1.0 deliverables:** Hosted demo at vigil.alexlaguardia.dev, pricing page, ProductHunt launch.

---

## v2.0.0 — "The Platform" (future)
> Goal: Multi-tenant, team features, hosted revenue.

- [ ] Hosted tier: $19/mo (solo), $49/mo (team)
- [ ] Multi-tenant: project isolation, team invites
- [ ] Policy engine: define what agents can access/modify per frame
- [ ] Pluggable memory backends: Mem0, Zep, Letta adapters (Vigil coordinates, they store)
- [ ] Agent marketplace: share frame configs + tool registries
- [ ] Metrics & analytics: signal volume, frame usage, agent uptime

---

## Phase 4 — Hardware (when software has traction)
> "Modern beeper" — physical device running Vigil

- [ ] Raspberry Pi-based always-on device
- [ ] E-ink display: awareness state, active agents, signal feed
- [ ] Physical LED indicators for frame state and alerts
- [ ] $99-149 hardware + subscription for hosted backend
- [ ] Target: after 100+ active users on hosted tier

---

## Competitive Landscape (as of 2026-03-21)

| Product | What It Does | Stars | Vigil Overlap |
|---------|-------------|-------|---------------|
| Mem0 | Graph memory for agents | ~8K | None — memory vs awareness |
| Letta (MemGPT) | Self-editing agent memory | ~15K | None — runtime vs infrastructure |
| Zep | Temporal knowledge graph | ~3K | None — fact tracking vs coordination |
| LangGraph | Stateful agent orchestration | ~25K | Low — orchestration vs awareness |
| OpenClaw | Viral agent runtime | ~210K | None — different layer entirely |
| NemoClaw | Enterprise agent platform | N/A | Low — enterprise vs indie |

**Vigil's unique features (no competitor has these):**
1. Background awareness daemon (compile → boot pattern)
2. Frame-based tool filtering with token budget savings
3. Signal protocol with content budgets
4. Session handoff chain
5. "Nervous system" positioning (coordination, not storage)

---

## Session Estimates

| Version | Sessions | Lines (est.) | Key Milestone |
|---------|----------|-------------|---------------|
| v0.5.0 | 3-4 | ~2,500 | MCP server mode + handoff |
| v1.0.0 | 5-8 | ~5,000 | REST API + dashboard |
| v2.0.0 | 10+ | ~8,000 | Hosted tier live |

**Priority order within each version:** Ship MCP server mode first (v0.5). It's the distribution channel. Everything else compounds on top of adoption.
