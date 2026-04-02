# Vigil Roadmap
> Cognitive infrastructure for AI agents — awareness, not just memory.
> Last updated: 2026-04-02
> Last competitive recon: 2026-04-02

## Strategic Position

Vigil is NOT a memory product. Mem0 ($24.5M raised, 51K stars), Letta ($10M, 22K stars), Zep ($2.3M, YC W24) — they store facts. Vigil **coordinates awareness**. The play: become the standard awareness layer that sits above any memory system. Complementary, not competitive.

**Honest position:** 0 stars, 0 paying customers, $0 funding. Competing for developer attention in a space with $500M+ in combined funding. Vigil wins by being small, focused, and solving a problem the big players ignore — not by out-featuring them.

**Moat:** Daemon pattern + frame-based filtering + signal protocol + session handoff + event triggers + MCPWatch. Nobody else has this combination. The funded players all focus on memory storage or agent orchestration — none do operational awareness.

**Wedge:** MCPWatch (MCP server observability). 97M monthly MCP SDK downloads, zero dedicated monitoring tools. This is the door in.

**Revenue path:** Open-source core → MCPWatch paid tier → hosted platform → enterprise.

---

## What's Shipped (v0.1 → v2.2)

Built v0.1 to v2.2 in 10 days (2026-03-19 to 2026-03-28). 8,400+ lines, 311 tests, 4 PyPI releases.

**Core (free, open source):**
- Awareness daemon (90s compile cycle)
- Frame-based tool filtering (50-90% token savings)
- Signal protocol (4 types, content budgets)
- Session handoff chains (structured continuity between agents)
- Signal compaction (tiered: raw → daily → weekly → monthly)
- Event triggers (pattern → webhook/signal/focus/log)
- Knowledge base (key-value with fuzzy recall)
- CLI: 14 commands + tab completion + quickstart wizard + doctor
- MCP server: 13 tools, stdio + SSE transports
- REST API: 20 endpoints, Bearer auth, SSE event stream
- Dashboard: 5 pages with real-time updates
- SQLite storage (zero infrastructure)
- PyPI: `pip install vigil-agent` | npm: `vigil-agent`
- 6 integration examples (Claude Code, Cursor, GitHub Actions, Slack, Discord)

**MCPWatch (paid tier feature):**
- One-line SDK: `from vigil.mcpwatch import instrument; instrument(server)`
- Auto-emit signals on: tool calls, errors, latency spikes, connection drops
- MCP health dashboard: uptime, tool call volume, error rates, p95 latency
- Silent failure detection + latency degradation alerts
- Per-tool analytics + historical trends
- Multi-server view from one dashboard
- CLI health check + GitHub Action workflow
- Slack/webhook alert templates

**Hosted Platform (app.vigil-agent.com):**
- Multi-tenant with per-tenant SQLite isolation
- GitHub OAuth + Stripe billing
- API key management (vgl_ prefix, SHA-256 hashed)
- Usage metering + tier enforcement
- Rate limiting per tier
- Audit log with REST endpoint
- Real-time signal stream (WebSocket)
- Signal analytics (hourly volume, type distribution, agent table)
- Onboarding: 3-step guided setup

**Distribution done:**
- PyPI v2.2.0 + npm v0.1.0
- 2 Dev.to articles published
- mcp.so + mcpservers.org listed
- awesome-mcp-servers PR merged (appcypher, 5.2K stars)
- LinkedIn launch post
- Landing page + onboarding deployed
- Domain: vigil-agent.com + app.vigil-agent.com

---

## Phase 1 — "Get Users" (Q2 2026)
> Goal: 100 GitHub stars, 500 PyPI downloads/week, 10 active installs. Prove someone besides Alex uses this.

### Distribution (finish what's started)
- [ ] HN "Show HN" (need karma — build via comments first)
- [ ] ProductHunt launch
- [ ] Reddit: r/LocalLLaMA, r/ClaudeAI (drafts ready in launch/REDDIT_POSTS.md)
- [ ] Dev.to article: "MCPWatch: Monitor Your MCP Servers Before They Silently Break"
- [ ] Dev.to article: "Session Handoff: How to Make AI Agents Pick Up Where Others Left Off"

### MCPWatch as the Wedge
- [ ] Standalone `vigil mcpwatch` CLI mode (no full Vigil setup needed — just monitor)
- [ ] 60-second quickstart: `pip install vigil-agent && vigil mcpwatch --server ./my_server.py`
- [ ] MCPWatch landing section on vigil-agent.com with before/after demo
- [ ] GitHub Action: `vigil-mcp-health-check` as a reusable workflow

### Pluggable Memory Backends (turn competitors into allies)
- [ ] Mem0 adapter: Vigil coordinates awareness, Mem0 handles deep memory
- [ ] Zep adapter: temporal knowledge graph as memory backend
- [ ] Plugin API: `class MemoryBackend(Protocol)` — bring your own
- [ ] Blog post: "Vigil + Mem0: Awareness Meets Memory" (cross-promote)

### DX Polish
- [ ] Better error messages across all CLI commands
- [ ] `vigil import` — import config from another project
- [ ] Docker image: `docker run vigil`

---

## Phase 2 — "First Revenue" (Q3-Q4 2026)
> Goal: 10-20 paying customers, $300-1K/mo MRR.

### Pricing Adjustment
Current pricing is too low — competing against free tiers of funded companies at $9/mo is a losing game.

| Tier | Price | Target |
|------|-------|--------|
| Free | $0 | 1 project, 2 agents, 5K signals/mo, no MCPWatch |
| Pro | $29/mo | 3 projects, unlimited agents, 50K signals/mo, MCPWatch, dashboard |
| Team | $79/mo | 10 projects, SSO, 200K signals/mo, priority support |
| Enterprise | $199/mo | Unlimited, SLA, custom frames, dedicated support |

### Dashboard Improvements
- [ ] Handoff timeline visualization
- [ ] Frame switching UI
- [ ] Trigger builder (visual rule editor)
- [ ] Alert system: email/Slack/webhook on metric thresholds

### Production Hardening
- [ ] Postgres adapter for hosted tier (replace per-tenant SQLite at scale)
- [ ] Redis adapter for high-throughput signal bus
- [ ] Team invites with role-based access (admin/member/viewer)
- [ ] Content filters (block signals containing PII/secrets)

---

## Phase 3 — "Grow or Die" (2027)
> Goal: $3-8K/mo MRR. Decide if Vigil justifies continued investment.

### If traction is real (>50 paying customers):
- [ ] Letta adapter (self-editing memory runtime)
- [ ] Go SDK + Rust SDK
- [ ] CLI installers: brew, apt, winget
- [ ] Per-frame access control (which agents see what)
- [ ] Signal permissions (which agents can emit what)
- [ ] Enterprise SSO (SAML, OIDC)
- [ ] SOC 2 Type II audit trail

### If traction is weak (<20 paying customers):
- Evaluate: is this a product the market wants, or a project Alex built for himself?
- Options: pivot MCPWatch into standalone product, open-source everything and walk away, or find a specific vertical (e.g., AI coding agents only)

---

## Competitive Landscape (as of 2026-04-02)

### Memory Layer (complementary — Vigil sits above these)
| Product | Stars | Funding | What They Do | Vigil Integration |
|---------|-------|---------|-------------|-------------------|
| Mem0 | 51,793 | $24.5M | Graph memory, API-first | Adapter planned |
| Supermemory | 20,927 | $3M | #1 LongMemEval, auto profiling | Potential adapter |
| Cognee | 14,867 | $7.5M | Knowledge graph engine, Rust edge | Watch |
| Letta | 21,863 | $10M | Self-editing memory runtime | Adapter planned |
| Zep | 4,351 | $2.3M | Temporal knowledge graph | Adapter planned |
| Interloom | NEW | $14.2M | Expert knowledge capture | Watch |

### Agent Frameworks (different layer — Vigil adds awareness to these)
| Product | Stars | Funding | What They Do | Overlap |
|---------|-------|---------|-------------|---------|
| AutoGen | 56,615 | Microsoft | Multi-agent conversation | Low (fragmented, 4 forks) |
| CrewAI | 47,850 | $24.5M | Role-based multi-agent | Low (4 unpatched security vulns) |
| LangGraph | 28,251 | $260M | Stateful graph orchestration | Low (3 critical vulns Mar 2026) |
| Semantic Kernel | 27,624 | Microsoft | .NET AI orchestration SDK | None |
| Haystack | 24,687 | $45.6M | RAG pipeline framework | None |

### Adjacent / Watch
| Product | Stars | Funding | What They Do | Threat Level |
|---------|-------|---------|-------------|-------------|
| Hyperspell | NEW | YC F25 | Memory via workplace connectors | Low (different approach) |
| Reload | NEW | $2.3M | AI workforce management | Medium (closest to Vigil's problem) |
| MemOS | NEW | OSS | Memory operating system for LLMs | Low (academic) |
| Mnemosyne | NEW | OSS | 5-layer cognitive memory | Low (unproven) |

### Dead
| Product | What Happened |
|---------|--------------|
| Julep | Hosted product shut down Dec 2025. Pivoted to Claude Code plugin. |

---

## Revenue Projections (realistic)

| Phase | Timeline | MRR | Driver |
|-------|----------|-----|--------|
| Open Source | Now - Q2 2026 | $0 | Stars, downloads, content marketing |
| First Paying Users | Q3 2026 | $100-300 | MCPWatch early adopters |
| Early Growth | Q4 2026 | $500-1K | Word of mouth, Dev.to pipeline |
| Validation Point | Q1 2027 | $1-3K | 50+ paying users = product-market signal |
| Growth or Pivot | Q2-Q4 2027 | $3-8K | If traction holds, push to $10K |
| Ceiling (solo founder) | 2028 | $5-15K/mo | Without funding or team, this is the cap |

**Break-even for hosted tier:** ~20 Pro customers ($29/mo) or ~8 Team customers ($79/mo).

**Honest ceiling:** A solo founder with no funding competing against $500M+ in the space will cap at $5-15K/mo unless Vigil finds a viral wedge (MCPWatch?) or gets acquired as infrastructure by a bigger player.

---

## Key Metrics to Track

| Metric | Current | Q2 2026 Target | Q4 2026 Target |
|--------|---------|----------------|----------------|
| PyPI downloads/week | ~0 | 500 | 2,000 |
| GitHub stars | 0 | 100 | 500 |
| Active installs | 1 (ours) | 10 | 50 |
| Paying customers | 0 | 0 | 10-20 |
| MRR | $0 | $0 | $500-1K |
| Tests | 311 | 350 | 400 |

---

## What's NOT on the Roadmap Anymore

These were in previous versions. Removed because they're premature or delusional at current scale:

| Cut | Why |
|-----|-----|
| Vigil Hub hardware ($99-149 device) | 0 customers. Hardware with no revenue is insanity. |
| Vigil Mobile (iOS + Android app) | Same. Build when there are 1,000+ users. |
| Vigil Earpiece | Cool sci-fi. Not a business plan. |
| Federation protocol (Vigil-to-Vigil relay) | Over-engineering for 1 user. Revisit at 100+ tenants. |
| Agent marketplace | No ecosystem to build a marketplace on. |
| Multi-language SDKs (Go, Rust) | TypeScript SDK shipped. Go/Rust when demand exists. |
| $50K+/mo steady state projection | Fantasy. Replaced with honest $5-15K/mo solo ceiling. |
