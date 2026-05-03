# MCPWatch Outreach Plan

Goal: Drive MCPWatch adoption among MCP server maintainers and users. Each adoption = stars + word of mouth + case study.

---

## Status (2026-05-03)

**Phase 1 outreach result: 0 conversions, 1 ban, 1 closed.**

| Repo | Stars | Result |
|---|---|---|
| tadata-org/fastapi_mcp #303 | 11.8K | Open, no engagement |
| oraios/serena #1441 | 23.6K | Closed: "not something we need" |
| BeehiveInnovations/pal-mcp-server #440 | 11.5K | Open, no engagement |
| mrexodia/ida-pro-mcp #391 | 8K | **Banned**: maintainer claimed project doesn't use FastMCP |

### Root cause of failure

All four targets import the official `mcp` SDK (low-level `Server`), **not** the third-party `fastmcp` package. MCPWatch only instrumented FastMCP. Pitch claim ("wraps any FastMCP server") was scope-mismatched at every target. ida-pro-mcp's maintainer caught the mismatch and treated it as spam.

### Fix shipped (this session)

- MCPWatch v2.3.0 now instruments **both** FastMCP and low-level `mcp.Server` (one line, polymorphic dispatch)
- Dev.to article scope claim patched live: "any Python MCP server — FastMCP and low-level Server, same API"
- 7 new tests covering low-level path, all 317 existing tests still green

---

## Outreach Template v2 (/copy voice)

Old opener: "Hey team. fastapi_mcp user here..." — generic, says nothing specific.

New opener: lead with their pain, land with a confident short solution.

### Issue title

`MCP observability for {repo} users`

### Issue body

```markdown
MCP servers fail silently. A tool returns empty results, the agent works around it, you find out three days later. No log, no alert.

I built MCPWatch to catch this. One line wraps any Python MCP server — FastMCP, low-level Server, same call. Per-tool latency, error rates, silent-failure detection.

```python
from vigil.mcpwatch import instrument
watch = instrument(server)
```

For {repo} specifically: {one-sentence niche relevance — what their users would care about}.

Open source, MIT. Happy to send a tested integration example if useful.

Repo: https://github.com/AlexlaGuardia/Vigil
Article: https://dev.to/alexlaguardia/your-mcp-servers-are-flying-blind-heres-how-to-fix-it-3g51
```

### Niche-relevance fragments to swap in

- **fastapi_mcp**: "users running production FastAPI deployments need per-tool latency to catch regressions before they hit agents."
- **pal-mcp-server**: "multi-LLM proxies are latency-sensitive — p95 spikes per provider matter more than aggregate."
- **serena**: ❌ closed, do not re-engage
- **ida-pro-mcp**: ❌ banned, do not re-engage
- **{new FastMCP target}**: write fresh per repo

---

## Awesome-List PR Entry v2 (/copy voice)

Old (41 words, generic, says nothing strong):
> "One-line observability for any FastMCP server. Tracks tool latency (p50/p95/p99), error rates, silent failures, and call volume. REST API + CLI + alerts. Free, MIT."

New (25 words, leads with outcome, ends strong):
> **Vigil MCPWatch** — One line catches every silent MCP failure. Tracks latency, errors, and empty returns across every registered tool. FastMCP and low-level Server. MIT.

### Markdown entry (paste-ready)

```markdown
- [Vigil MCPWatch](https://github.com/AlexlaGuardia/Vigil) - One line catches every silent MCP failure. Tracks latency, errors, and empty returns across every registered tool. FastMCP and low-level Server. MIT.
```

### PR title

`Add Vigil MCPWatch — observability for any Python MCP server`

### PR body

```markdown
Adds Vigil MCPWatch under tools/observability.

MCPWatch wraps any Python MCP server in one line — both `FastMCP` and the low-level `mcp.server.lowlevel.Server`. Tracks:

- Tool call latency (p50/p95/p99)
- Per-tool error rates
- Silent failures (empty/null returns + isError responses)
- Call volume over time

Used in production across 95+ MCP tools. MIT, no config required.

Article: https://dev.to/alexlaguardia/your-mcp-servers-are-flying-blind-heres-how-to-fix-it-3g51
```

---

## Tier 2: Awesome-List Submission Targets

Submit MCPWatch under tools/observability section.

| List | Repo | Status |
|------|------|--------|
| 1 | punkpeye/awesome-mcp-servers | TODO |
| 2 | wong2/awesome-mcp-servers | TODO |
| 3 | tolkonepiu/best-of-mcp-servers | TODO (auto-ranked, may need scraper-friendly entry) |
| 4 | habitoai/awesome-mcp-servers | TODO |
| 5 | rohitg00/awesome-devops-mcp-servers | TODO (best fit — DevOps/observability scope) |

Execution order on PAT refresh: **5 → 1 → 2 → 4 → 3** (best fit first, auto-ranked last).

---

## Tier 1: Future Outreach (FastMCP-verified targets only)

**Lesson:** Verify each target imports `mcp.server.fastmcp.FastMCP` OR uses the low-level `mcp.Server` API before sending. Read their `pyproject.toml` and at least one server file. If they don't use either, skip.

Target identification command (manual):
```bash
# For each candidate repo:
curl -s "https://api.github.com/search/code?q=from+mcp.server.fastmcp+import+FastMCP+repo:{owner/repo}"
```

### Candidate pipeline (TBD — needs research session)

Target list to be built next session via GitHub code-search filtered by stars > 500.

---

## Tier 3: Community Channels (when ready)

- modelcontextprotocol Discord — share article in #show-and-tell
- r/LocalLLaMA, r/ClaudeAI — when Reddit account is warm
- HN — Show HN when karma allows

---

## Tone Rules (steal sheet)

- Lead with the user's pain, not your tool's features
- Use niche language ("silent failure", "p95", "FastMCP", "low-level Server")
- One specific example per pitch — never list 5 features
- End on strong word
- No "Hey team", no "Wanted to flag", no "in case it's useful"
- Always link the Dev.to article — it does the selling
