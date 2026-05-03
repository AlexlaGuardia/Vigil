# PAT Resume Checklist

Tonight (2026-05-03) shipped Vigil v2.3.0 (low-level Server support) but the GitHub PAT is invalid — push, PyPI publish, and outreach PRs are queued for when you refresh the token.

Estimated time to clear this list: **~20 minutes.**

---

## Step 1: Refresh GitHub PAT (5 min)

1. https://github.com/settings/tokens → "Generate new token (classic)"
2. Scopes needed: `repo` (full), `workflow`, `write:packages` (if publishing GH packages)
3. Set expiration: 90 days
4. Copy the token

Update local credentials:

```bash
# Update gh CLI
echo "<new-token>" | gh auth login --with-token

# Verify
gh auth status

# Update Vigil remote (current remote has dead embedded PAT)
cd /root/vigil
git remote set-url origin https://x-access-token:<new-token>@github.com/AlexlaGuardia/Vigil.git
```

Save the new token to `.env` if your tooling reads it:

```
GITHUB_PAT=ghp_xxx
```

---

## Step 2: Push Vigil v2.3.0 (2 min)

```bash
cd /root/vigil
git add vigil/mcpwatch.py vigil/__init__.py pyproject.toml tests/test_mcpwatch.py launch/DEVTO_MCPWATCH.md launch/MCPWATCH_OUTREACH.md launch/PAT_RESUME.md
git commit -m "v2.3.0: MCPWatch low-level Server support

Adds polymorphic dispatch in instrument() — wraps both FastMCP
(_tool_manager.tools) and low-level mcp.Server (request_handlers
[CallToolRequest]) with the same one-line API.

Detects low-level isError responses (Server wraps user exceptions
as CallToolResult instead of propagating).

Bumps version to 2.3.0. 7 new tests, all 317 existing pass."

git push origin main
```

---

## Step 3: Publish to PyPI (3 min)

```bash
cd /root/vigil
rm -rf dist/ build/ *.egg-info
python3 -m build
twine upload dist/*
# Username: __token__
# Password: <pypi-token from .env or 1pass>
```

Verify: https://pypi.org/project/vigil-agent/2.3.0/

---

## Step 4: Submit 5 Awesome-List PRs (10 min)

**Order: best-fit first, auto-ranked last.**

For each: fork → add entry → PR. Paste-ready entry markdown:

```markdown
- [Vigil MCPWatch](https://github.com/AlexlaGuardia/Vigil) - One line catches every silent MCP failure. Tracks latency, errors, and empty returns across every registered tool. FastMCP and low-level Server. MIT.
```

PR title: `Add Vigil MCPWatch — observability for any Python MCP server`

PR body (copy from `MCPWATCH_OUTREACH.md` Awesome-List section):

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

### Targets

1. **rohitg00/awesome-devops-mcp-servers** (best fit — DevOps/observability scope)
   - https://github.com/rohitg00/awesome-devops-mcp-servers
   - Add under any Monitoring/Observability section, or create one.

2. **punkpeye/awesome-mcp-servers**
   - https://github.com/punkpeye/awesome-mcp-servers
   - Add under "Tools" or similar.

3. **wong2/awesome-mcp-servers**
   - https://github.com/wong2/awesome-mcp-servers
   - Original/oldest list.

4. **habitoai/awesome-mcp-servers**
   - https://github.com/habitoai/awesome-mcp-servers
   - Newer, accepts submissions.

5. **tolkonepiu/best-of-mcp-servers** (auto-ranked)
   - https://github.com/tolkonepiu/best-of-mcp-servers
   - Check their submission format before opening — may want a YAML entry instead of markdown line.

### Speedrun via gh CLI (optional)

```bash
# For each target:
gh repo fork rohitg00/awesome-devops-mcp-servers --clone --remote
cd awesome-devops-mcp-servers
git checkout -b add-mcpwatch
# edit README.md, paste entry
git add README.md
git commit -m "Add Vigil MCPWatch"
git push origin add-mcpwatch
gh pr create --title "Add Vigil MCPWatch — observability for any Python MCP server" --body-file ../vigil/launch/PR_BODY.md
```

---

## Optional: Skip the queue

If you just want one shipped tonight, do **#1 (rohitg00/awesome-devops-mcp-servers)**. It's the highest-fit list and the best chance of a quick merge. The other four can wait.

---

## What's NOT in this list (intentionally)

- **No re-engagement with serena (#1441) or ida-pro-mcp (#391)** — both closed, ida-pro-mcp banned. Burned bridges.
- **No new direct outreach** — Tier 1 outreach is paused until we build a verified target list (FastMCP-importing or `mcp.Server`-using repos with stars > 500).
- **No Reddit/HN posts** — both channels are karma-gated and dead for now.

---

## Cortex signal to log after Step 2

```bash
curl -s -X POST "https://mcp.guardiacontent.com/mcp/call?key=guardia-hq-ff08357c6af38280" \
  -H "Content-Type: application/json" \
  -d '{"tool":"cortex_signal","arguments":{"content":"Vigil v2.3.0 shipped — MCPWatch now wraps low-level mcp.Server alongside FastMCP. Pushed to GitHub + PyPI.","from_agent":"alex"}}'
```
