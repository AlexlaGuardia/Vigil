---
title: "Your MCP Servers Are Flying Blind (Here's How to Fix It)"
published: false
description: "Most MCP servers have zero observability. No error tracking, no latency metrics, no alerts. I built MCPWatch to fix that."
tags: mcp, ai, python, monitoring
cover_image: https://raw.githubusercontent.com/AlexlaGuardia/Vigil/main/cover.png
---

## The Problem

You deploy an MCP server. Agents start calling tools. Something breaks.

How do you know?

Right now, you don't. Most MCP servers are black boxes. No metrics. No error rates. No latency tracking. No alerts when a tool starts failing silently.

I run 95 MCP tools across multiple projects. When a tool started returning empty results instead of errors, I didn't notice for three days. The agent just quietly worked around it, producing subtly wrong output. No crash, no log, no alert.

That's when I built MCPWatch.

## What MCPWatch Does

MCPWatch wraps any FastMCP server with a single line of code and gives you full operational visibility:

```python
from vigil import MCPWatch

watch = MCPWatch(server)
```

That's it. From that point, every tool call is tracked:

- **Call volume** per tool (which tools are actually used?)
- **Duration** with p50/p95/p99 percentiles (what's slow?)
- **Error rates** per tool (what's failing?)
- **Latency trends** (is performance degrading?)
- **Silent failures** (tool returned successfully but with empty/null data)

## The Dashboard

MCPWatch exposes 5 REST endpoints for monitoring:

```
GET /mcp/health    -- overall server health (healthy/degraded/unhealthy)
GET /mcp/tools     -- per-tool stats breakdown
GET /mcp/errors    -- recent errors with full context
GET /mcp/latency   -- latency percentiles per tool
GET /mcp/volume    -- call volume over time
```

There's also a CLI command:

```bash
vigil mcp-health
```

This gives you a per-tool breakdown right in your terminal. I run it before and after deploys.

## Alerts

MCPWatch emits alerts when things go wrong:

```python
watch = MCPWatch(
    server,
    error_threshold=0.1,     # alert if >10% of calls fail
    latency_threshold=5000,  # alert if p95 > 5 seconds
)
```

Alerts flow through Vigil's signal protocol, which means you can wire them to webhooks, Slack, or any trigger action.

## CI/CD Health Check

For CI pipelines, there's a stdio probe:

```bash
vigil mcp-health-check --timeout 5000 --min-tools 10 --require query,signal
```

Returns exit code 0 (healthy) or 1 (unhealthy). Drop it into GitHub Actions:

```yaml
- name: MCP Health Check
  run: vigil mcp-health-check --timeout 5000 --min-tools 10
```

## Why This Matters

The MCP ecosystem is growing fast. There are 11,000+ servers listed across registries. But the tooling around MCP is still in the "deploy and pray" phase.

In traditional web services, you'd never deploy an API without monitoring. MCP servers deserve the same treatment. Especially when the consumer is an AI agent that won't tell you something is wrong -- it'll just silently degrade.

## Getting Started

```bash
pip install vigil-agent
```

MCPWatch is part of Vigil, a broader cognitive infrastructure toolkit for AI agents. But you can use MCPWatch standalone -- just wrap your server and point your monitoring at the endpoints.

The full docs and source are on GitHub. MIT license.

---

*I'm building tools for AI agent infrastructure. If you're running MCP servers in production, I'd love to hear what observability problems you're hitting. Drop a comment or find me on GitHub.*
