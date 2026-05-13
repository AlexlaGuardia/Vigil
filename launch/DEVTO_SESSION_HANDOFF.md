---
title: "Your AI Agent Forgets Everything Between Sessions (Here's How to Fix It)"
published: false
description: "Session handoff is the missing piece in multi-session AI workflows. Here's the protocol I built to keep agents in sync across sessions."
tags: ai, python, claudecode, productivity
cover_image: https://raw.githubusercontent.com/AlexlaGuardia/Vigil/main/cover.png
---

## The Problem

You finish a session with Claude Code at 11pm. Three files changed, two design decisions made, one bug discovered but unresolved.

You start fresh the next morning. The agent has no memory of any of it.

You spend the first ten minutes of the new session doing what I call "cold-start theater": re-reading the changed files, re-explaining what you decided yesterday, re-discovering the bug you already debugged.

Multiply that by every session. That's the tax you pay for stateless agents.

## Why Conversation History Doesn't Solve This

The obvious answer is "just save the conversation." It doesn't work for three reasons:

1. **Conversation history is enormous.** A real working session has thousands of messages, tool calls, and outputs. Loading it consumes most of your context window before you do anything useful.

2. **It's mostly noise.** 90% of what happened in the previous session was the agent reasoning out loud. The next agent doesn't need that. It needs the conclusions.

3. **It doesn't compose across agents.** If agent A finishes a task and agent B picks up later, B doesn't want to read A's monologue. B wants to know what changed and what's next.

## What a Handoff Actually Needs

After running multi-agent setups for a year, the pattern that works is a structured summary with five fields:

- **Files touched**: what physically changed on disk
- **Decisions made**: architectural or design choices that affect future work
- **Blockers**: things that stopped progress, with enough context to unblock
- **Next steps**: what the next agent should do first
- **Open threads**: anything unresolved that future-you needs to remember

That's it. Five fields, usually under 500 words. The next agent reads this in under a second and has full operational awareness.

## The Protocol

In Vigil, handoff is a first-class operation:

```python
from vigil import Vigil

v = Vigil()
v.handoff(
    agent="backend-cc",
    files_touched=["api/routes.py", "models/user.py"],
    decisions=["Switched to JWT auth from sessions; simpler refresh flow"],
    blockers=["Stripe webhook still failing in test mode, see line 142"],
    next_steps=["Wire JWT middleware into protected routes", "Fix Stripe webhook signature validation"],
    open_threads=["Decide on rate limit strategy before deploy"],
)
```

When the next agent boots:

```python
context = v.resume(agent="backend-cc")
# Returns the most recent handoff, or chains across the last N
```

Or via the CLI:

```bash
vigil resume backend-cc
```

The handoff is stored as structured data, queryable, and the daemon includes the most recent handoff in the agent's awareness file automatically.

## Handoff Chains

The thing that surprised me when I built this: chains compound.

If you handoff three sessions in a row on the same project, the next agent can resume the *chain*. It sees the most recent handoff plus a summarized rollup of the previous two. No information loss across multiple sessions.

```bash
vigil resume backend-cc --chain 5
```

Returns a synthesized view of the last five handoffs. Decisions persist. Blockers either get resolved (and removed) or carry forward (and become urgent).

This is how you keep continuity across days or weeks of work without ever loading a full conversation history.

## Why MCP Wasn't Enough

I tried to do this through MCP at first: just expose handoff tools to Claude Code and let the agent emit them.

That works, but it's not enough. The handoff needs to live somewhere the next agent can read *before* tools are even loaded. Tool calls cost a round trip. The handoff should be in your boot context.

The pattern that works: handoff data lands in the awareness file. Agents read awareness on boot. Zero tool calls needed to know what happened last session.

## Concrete Numbers

Before this protocol: my agents spent 8-15K tokens per session re-discovering context.

After: the awareness file with embedded handoff is ~2K tokens, loaded once at boot. The token savings show up directly on my Anthropic bill.

The bigger win is psychological: I stopped dreading the start of new sessions. The agent knows where we left off.

## Getting Started

```bash
pip install vigil-agent
vigil init
```

Handoff is a core feature of Vigil, alongside the awareness daemon, frame-based tool filtering, and the signal protocol. Full docs and source on GitHub. MIT license.

If you're running multi-session AI workflows and you've felt the cold-start tax, give it a try. I'd love to hear what handoff protocol works for your setup.

---

*I'm building cognitive infrastructure for AI agents. If session handoff is something you're solving for, drop a comment or find me on GitHub.*
