# Vigil Roadmap
> Cognitive infrastructure for AI agents — awareness, not just memory.
> Last updated: 2026-03-21

## Strategic Position

Vigil is NOT a memory product. Mem0, Letta, Zep — they store facts. Vigil **coordinates awareness**. The play: become the standard awareness layer that sits above any memory system. Complementary, not competitive.

**Moat:** Daemon pattern + frame-based filtering + signal protocol + session handoff + event triggers. Nobody else has this combination. The MCP ecosystem (97M monthly SDK downloads, 10K+ servers) is the distribution channel.

**Revenue path:** Open-source core → hosted tier → enterprise → hardware device.

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

## v0.5.0 — SHIPPED (2026-03-21)
> 3,972 lines, 10 modules, 133 tests

- [x] Session handoff protocol (HandoffProtocol, structured continuity, handoff chains)
- [x] Signal compaction engine (tiered: raw → daily → weekly → monthly)
- [x] MCP server mode (12 tools, stdio + SSE transports)
- [x] Agent identity (agents table, auto-register, scoped queries)
- [x] CLI: 14 commands (serve, handoff, resume, history, agents, compact)
- [x] Full code audit — unified MCP/CLI data paths, zero dead code
- [x] PyPI v0.5.0 published

---

## v1.0.0 — SHIPPED (2026-03-21)
> 5,922 lines, 13 modules, 196 tests. Built v0.1→v1.0 in a single session.

- [x] REST API — FastAPI, 20 endpoints, Bearer + header auth
- [x] SSE /events stream for real-time signal feed
- [x] Dashboard — 5 pages (overview, agents, signals, handoffs, frames)
- [x] htmx live updates (awareness 10s, signals 5s polling)
- [x] Event triggers — 4 action types (webhook, signal, focus, log)
- [x] Pattern matching (signal_type, agent glob, content regex)
- [x] Trigger management via MCP, REST, and CLI
- [x] 3 transport modes: stdio (MCP), SSE (MCP), HTTP (REST + dashboard)
- [x] `mcp` as optional dependency (core works without it)
- [x] PyPI v1.0.1 published

---

## v1.5.0 — "The Adoption Release" — SHIPPED (2026-03-28)
> Goal: Get Vigil into the hands of 1,000 developers. Distribution + DX polish.

### Launch Campaign
- [x] HN "Show HN" post updated for v1.5 (submit Thu 8-10am ET)
- [x] Dev.to article: "I Built a Nervous System for AI Agents (Not Another Memory Store)" — published 2026-03-25
- [x] Dev.to article: "How I Built a Full Product in One Night with 3 Parallel AI Agents" — published 2026-03-25
- [x] Registry configs: smithery.yaml + glama.json committed (auto-indexing)
- [x] Cover image generated and committed
- [x] Portfolio site: Vigil project card (v1.5 stats)
- [x] v1.5.0 published to PyPI
- [x] MCP registry: mcp.so — submitted 2026-03-28
- [x] MCP registry: mcpservers.org — submitted 2026-03-28
- [x] awesome-mcp-servers PR (appcypher, 5.2K stars) — merged 2026-03-28
- [x] LinkedIn launch post — posted 2026-03-28
- [ ] HN "Show HN" — deferred (new account needs karma first)
- [ ] Reddit: r/LocalLLaMA, r/ClaudeAI — deferred (drafts ready in launch/REDDIT_POSTS.md)
- [ ] ProductHunt launch — deferred

### DX Polish
- [x] `vigil quickstart` — interactive setup wizard (init + register frames + first signal + daemon start)
- [x] `vigil doctor` — diagnose common issues (DB exists? daemon running? signals flowing?)
- [x] `vigil export` — dump awareness state + recent handoffs to markdown (for pasting into Claude/GPT)
- [ ] `vigil import` — import a Vigil config from another project (frames, triggers)
- [ ] Better error messages across all CLI commands
- [x] `vigil version` command
- [x] Tab completion for bash/zsh

### Integrations
- [x] Claude Code hook: auto-emit signals on tool calls (CLAUDE.md example)
- [x] GitHub Actions integration: emit signals from CI (deploy success/fail → triggers)
- [x] Slack webhook template: alert triggers → Slack channel
- [x] Discord webhook template
- [x] Example: Vigil + Cursor (`.cursor/mcp.json` config)
- [x] Example: Vigil + Claude Desktop
- [ ] Example: Vigil + n8n/Zapier (webhook triggers as automation source)

### Knowledge Base
- [x] `knowledge` table: key, value, category, source_agent, confidence, created_at
- [x] `vigil know <key> <value>` CLI + MCP tool + REST endpoint
- [x] `vigil recall <query>` — fuzzy-match knowledge lookup
- [x] Knowledge != signals. Signals are ephemeral. Knowledge persists and accumulates.
- [x] Auto-extract: daemon identifies recurring patterns in signals → suggests knowledge entries

---

## v2.0.0 — "The Platform" (Q3 2026)
> Goal: Multi-tenant hosted service. The thing that generates revenue.

### Hosted Tier — vigil-agent.com
- [ ] Cloud-hosted Vigil instances (one-click setup)
- [ ] Free tier: 1 project, 2 agents, 5K signals/mo (generous enough to actually use)
- [ ] Pro tier: $9/mo (1 project, unlimited agents, 50K signals/mo, dashboard)
- [ ] Team tier: $29/mo (5 projects, unlimited agents, 200K signals/mo, SSO)
- [ ] Enterprise tier: $99/mo (unlimited, SLA, priority support, custom frames)
- [ ] Stripe billing integration
- [ ] Domain: vigil-agent.com (matches PyPI package name)

### Multi-Tenant Architecture
- [ ] Project isolation: each project gets its own SQLite DB (or Postgres for scale)
- [ ] Team invites: email-based, role-based (admin/member/viewer)
- [ ] API key management: per-project keys with scopes
- [ ] Usage metering: signal count, agent count, storage, compile cycles
- [ ] Rate limiting per tier
- [ ] Audit log: who did what, when (compliance-ready)

### Policy Engine
- [ ] Per-frame access control: which agents can access which frames
- [ ] Signal permissions: which agents can emit which signal types
- [ ] Tool execution policies: rate limits, approval gates
- [ ] Content filters: block signals containing sensitive patterns (PII, secrets)
- [ ] Admin override: manual frame switching, signal injection

### Advanced Dashboard
- [ ] Real-time signal stream (WebSocket, not htmx polling)
- [ ] Signal analytics: volume over time, type distribution, agent activity heatmap
- [ ] Handoff timeline visualization (Gantt-style)
- [ ] Frame switching UI (click to change active frame)
- [ ] Trigger builder: visual rule editor (no JSON editing)
- [ ] Alert system: email/Slack/webhook when metrics cross thresholds
- [ ] Mobile-responsive layout

### Pluggable Memory Backends
- [ ] Mem0 adapter: Vigil coordinates awareness, Mem0 handles deep memory
- [ ] Zep adapter: temporal knowledge graph as memory backend
- [ ] Letta adapter: self-editing memory runtime
- [ ] Redis adapter: for ephemeral high-throughput signal buses
- [ ] Postgres adapter: for hosted tier scale (replace SQLite)
- [ ] Plugin API: `class MemoryBackend(Protocol)` — bring your own

---

## v3.0.0 — "The Network" (Q4 2026 / Q1 2027)
> Goal: Vigil instances talking to each other. Cross-organization agent coordination.

### Federation Protocol
- [ ] Vigil-to-Vigil signal relay: instance A emits → federated to instance B
- [ ] Selective federation: choose which signal types/frames to share
- [ ] Trust model: approve/deny federation requests between instances
- [ ] Signal namespacing: `project:agent:signal` to avoid collisions
- [ ] Federated awareness: compile awareness across multiple instances

### Agent Marketplace
- [ ] Share frame configurations (curated sets for common workflows)
- [ ] Share trigger templates (CI/CD, monitoring, team coordination)
- [ ] Community-contributed integration examples
- [ ] Rating/review system
- [ ] Revenue share for premium templates

### SDK & Language Support
- [ ] TypeScript/Node SDK (`npm install vigil-agent`)
- [ ] Go SDK
- [ ] Rust SDK (for Supra integration and performance-critical use cases)
- [ ] CLI installers: brew, apt, winget, nix
- [ ] Docker image: `docker run vigil`

### Enterprise Features
- [ ] SSO: SAML, OIDC, Google Workspace, Okta
- [ ] Compliance: SOC 2 Type II audit trail
- [ ] Data residency: choose region for hosted instances
- [ ] Dedicated instances (single-tenant deployment)
- [ ] SLA: 99.9% uptime guarantee
- [ ] Priority support channel

---

## Phase 4 — "The Device" (2027)
> Physical hardware running Vigil. The modern beeper.

### Vigil Hub (Desktop)
- [ ] Raspberry Pi 5 based always-on device
- [ ] E-ink display: awareness state, active agents, signal feed, focus queue
- [ ] Physical LED ring: frame-colored ambient indicator (blue=backend, green=frontend, red=alert)
- [ ] Push-button: quick signal emit ("I'm starting work" / "I'm done")
- [ ] Always connected to hosted Vigil backend
- [ ] $99-149 hardware + hosted tier subscription
- [ ] OTA firmware updates

### Vigil Mobile
- [ ] Companion app (iOS + Android)
- [ ] Push notifications for alert signals and trigger fires
- [ ] Quick signal emit from phone
- [ ] Dashboard view on mobile
- [ ] Bluetooth connection to Vigil Hub for proximity features
- [ ] Wearable integration: Apple Watch / WearOS complication showing frame state

### Vigil Earpiece (stretch)
- [ ] Bone-conduction or earbud form factor
- [ ] Audio awareness: "You have 3 alerts. Backend agent deployed auth v2."
- [ ] Voice signal emit: "Signal: finished the migration"
- [ ] Wake word: "Hey Vigil" → voice interface
- [ ] Integrates with Luna voice pipeline (Akatskii)

---

## Competitive Landscape (as of 2026-03-21)

| Product | What It Does | Stars | Vigil Overlap | Vigil Advantage |
|---------|-------------|-------|---------------|-----------------|
| Mem0 | Graph memory | ~8K | None | Different layer — complementary |
| Letta (MemGPT) | Self-editing memory | ~15K | None | Runtime vs infrastructure |
| Zep | Temporal knowledge graph | ~3K | None | Fact tracking vs coordination |
| LangGraph | Stateful orchestration | ~25K | Low | Vigil is lighter, framework-agnostic |
| OpenClaw | Viral agent runtime | ~210K | None | Different layer entirely |
| NemoClaw | Enterprise agents | N/A | Low | Indie/dev-first vs enterprise-first |
| CrewAI | Multi-agent framework | ~25K | Low | Vigil is infra, CrewAI is framework |
| Symphony (OpenAI) | Agent orchestration | New | Low | Vigil is open, persistent, daemon-based |

**Vigil's moat (no competitor has all of these):**
1. Background awareness daemon (compile → boot pattern)
2. Frame-based tool filtering with token budget savings
3. Signal protocol with content budgets
4. Session handoff chain with structured continuity
5. Event triggers (pattern → action)
6. Tiered signal compaction
7. 3 transport modes (MCP stdio, MCP SSE, HTTP REST)
8. Embedded dashboard
9. "Nervous system" positioning (coordination, not storage)

---

## Revenue Projections

| Phase | Timeline | Revenue | Driver |
|-------|----------|---------|--------|
| Open Source | Now - Q2 2026 | $0 | GitHub stars, PyPI downloads, content |
| Early Hosted | Q3 2026 | $300-1K/mo | First paying users on pro/team tier |
| Hosted Growth | Q4 2026 | $2-8K/mo | Content marketing + word of mouth |
| Enterprise | Q1 2027 | $10-30K/mo | Enterprise tier + custom deployments |
| Hardware | Q3 2027 | +$10-30K/mo | Vigil Hub device + subscription |
| Steady State | 2028 | $50K+/mo | Platform + enterprise + hardware |

**Break-even for hosted tier:** ~50 pro customers or ~15 team customers.

---

## Key Metrics to Track

| Metric | Current | v1.5 Target | v2.0 Target |
|--------|---------|-------------|-------------|
| PyPI downloads/week | unknown | 500 | 2,000 |
| GitHub stars | 0 | 200 | 1,000 |
| Active Vigil instances | 1 (ours) | 50 | 500 |
| Paying customers | 0 | 0 | 30 |
| MRR | $0 | $0 | $1,500 |
| Tests | 268 | 300 | 400 |
| Lines of code | 7,500+ | 8,000 | 15,000 |
