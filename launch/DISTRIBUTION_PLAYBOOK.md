# Vigil Distribution Playbook
> Created 2026-04-18. Single source of truth for distribution execution.
> Goal: first 10 real users, first GitHub stars, build toward PH launch.

## Status Check (Apr 18)
- PyPI: 891 downloads/mo (21/wk) — some organic signal
- GitHub: 0 stars, 0 forks, 0 issues
- Hosted: app.vigil-agent.com live, Stripe wired, 0 paying users
- PH: not launched yet (saving for proper push)
- HN: karma 1 (need 10+ for Show HN)

---

## Phase 1: Listings (do this week — 30 min total)

### AlternativeTo
Go to https://alternativeto.net → Sign up → Add Application
- **Name:** Vigil
- **URL:** https://github.com/AlexlaGuardia/Vigil
- **Description:** Cognitive infrastructure for AI agents. Awareness daemon compiles system state every 90 seconds. Frame-based tool filtering cuts token usage 75-85%. Session handoff preserves context across sessions. MCP server with 12 tools. Works with Claude Code, Cursor, Claude Desktop.
- **Category:** Developer Tools → AI & Machine Learning
- **License:** MIT / Open Source
- **Platforms:** Linux, macOS, Windows (Python)
- **Alternatives to:** Mem0, Letta, LangGraph, CrewAI
- **Tags:** ai agents, mcp, cognitive infrastructure, awareness, developer tools

### AlternativeTo — Critik (while you're there)
- **Name:** Critik
- **URL:** https://critik.dev
- **Alternatives to:** Snyk, Semgrep, Bandit, SonarQube
- **Description:** AI-powered code security scanner. Two-pass architecture: regex/AST first, then Llama 3.3 AI review. Zero config CLI. VS Code extension. GitHub Action. Pre-commit hook. Free and open source.
- **Tags:** security, code scanner, ai, developer tools

### AlternativeTo — Stampwerk (while you're there)
- **Name:** Stampwerk
- **URL:** https://stampwerk.com
- **Alternatives to:** HoneyBook, Dubsado, Bonsai, AND.CO
- **Description:** AI-native freelancer business tool. AI-generated proposals, contracts, Stripe invoicing, and automated follow-up system. $12/mo.
- **Tags:** freelancing, invoicing, proposals, ai

### G2 (separate site)
Go to https://www.g2.com/products/new → submit for Vigil and Critik.
Same descriptions as above. G2 takes longer to approve but has strong SEO.

---

## Phase 2: Content (this week)

### Dev.to — MCPWatch Article (wedge content)
Draft at: /root/vigil/launch/DEVTO_MCPWATCH.md
Angle: "Your MCP Servers Are Flying Blind" — monitoring/observability for MCP
Target search: "MCP server monitoring", "MCP observability", "MCP production"
Publish on Dev.to with tags: mcp, ai, python, monitoring

### LinkedIn Post (ready to publish)
Draft at: /root/vigil/launch/LINKEDIN_POST_V2.md
Post during weekday morning (Tue-Thu 8-10am ET for max reach)

---

## Phase 3: Community (ongoing)

### HN Karma Building
- 1-2 comments per day on relevant threads (AI agents, MCP, developer tools)
- Quality over volume. Add real insight, not self-promo.
- Target: 10+ karma before attempting Show HN
- Show HN draft at: /root/vigil/launch/SHOW_HN.md (needs stats update to v2.2.0)

### Outreach Emails — Critik Listicles
Already drafted at /root/critik/launch/outreach-emails.md
3 Tier 1 targets:
1. CodeAnt.ai — AI code review tools list
2. GetPanto.ai — AI code review tools list
3. Krowdbase — AI vulnerability scanner list
Send from alex@alexlaguardia.dev or a.jinjurikii@gmail.com

---

## Phase 4: Launch (when ready)

### ProductHunt — Vigil
- **When:** After HN karma > 10 AND at least 5 GitHub stars
- **Critical lesson:** Be present for 4+ hours on launch day. Both Critik and Stampwerk fizzled because no same-day promo.
- **Prep:** Update gallery images, record demo GIF, prep LinkedIn + Dev.to + HN cross-posts for same day
- Show HN stats need updating: now v2.2.0, 311 tests, 8,400+ lines, 4 PyPI releases

---

## Quick Reference

| Channel | Status | Priority |
|---------|--------|----------|
| AlternativeTo | Not submitted | HIGH — do first |
| G2 | Not submitted | MEDIUM — do with AlternativeTo |
| Dev.to MCPWatch | Not written | HIGH — wedge content |
| LinkedIn | Draft ready | MEDIUM — post this week |
| HN karma | 1 (need 10+) | ONGOING — daily comments |
| HN Show HN | Draft ready (stale) | BLOCKED — karma |
| PH | Not launched | BLOCKED — stars + karma |
| Outreach emails | 3 drafted | LOW — send this week |
