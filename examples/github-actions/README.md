# Vigil + GitHub Actions

Emit Vigil signals from your CI/CD pipeline. Pushes, deployments, and PRs automatically show up in your awareness context.

## Prerequisites

1. A Vigil server running with HTTP transport:
   ```bash
   vigil serve --transport http --host 0.0.0.0 --port 8300
   ```

2. Add secrets to your GitHub repo:
   - `VIGIL_URL` — your server URL (e.g., `http://your-server:8300`)
   - `VIGIL_TOKEN` — your Vigil API Bearer token

## What Gets Signaled

| GitHub Event | Signal Type | Example |
|-------------|-------------|---------|
| Push to main | `observation` | "Push to main: Fix auth middleware" |
| Deploy success | `observation` | "Deployed to production successfully" |
| Deploy failure | `alert` | "Deployment to staging failed" |
| PR opened | `observation` | "PR opened: Add user dashboard (#42)" |
| PR merged | `observation` | "PR closed: Add user dashboard (#42)" |

## How It Works

The workflow sends HTTP POST requests to Vigil's REST API `/signals` endpoint. Signals are stored in the database, compiled by the daemon into awareness, and available to any agent on next boot.

Your AI agents (Claude Code, Cursor, etc.) will see these CI/CD events as part of their awareness context — no manual updates needed.

## Combine with Triggers

Set up Vigil triggers to react to CI/CD signals:

```bash
# Alert on deployment failures
vigil know "deploy-alert-trigger" "webhook" --category trigger

# Or via Python
from vigil import TriggerManager
triggers = TriggerManager(db)
triggers.create(
    name="deploy-failure-slack",
    signal_type="alert",
    agent_pattern="github-actions",
    content_pattern=".*failed.*",
    action_type="webhook",
    action_config={"url": "https://hooks.slack.com/..."},
)
```
