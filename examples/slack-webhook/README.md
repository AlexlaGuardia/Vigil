# Vigil + Slack

Route Vigil signals to Slack channels using event triggers.

## Setup

### 1. Create a Slack Incoming Webhook

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. Enable **Incoming Webhooks**
3. Add a webhook to your target channel
4. Copy the webhook URL

### 2. Create a Vigil Trigger

```python
from vigil import VigilDB, TriggerManager

db = VigilDB("vigil.db")
triggers = TriggerManager(db)

# Alert signals → Slack
triggers.create(
    name="alerts-to-slack",
    signal_type="alert",
    agent_pattern="*",
    action_type="webhook",
    action_config={
        "url": "https://hooks.slack.com/services/T.../B.../xxx",
        "method": "POST",
        "template": {
            "text": "Vigil Alert from {agent}: {content}"
        }
    },
)

# Deploy signals → Slack
triggers.create(
    name="deploys-to-slack",
    signal_type="observation",
    agent_pattern="github-actions",
    content_pattern=".*[Dd]eploy.*",
    action_type="webhook",
    action_config={
        "url": "https://hooks.slack.com/services/T.../B.../xxx",
        "method": "POST",
        "template": {
            "text": "Deploy: {content}"
        }
    },
)
```

### 3. Verify

```bash
# Emit a test alert
vigil signal test-agent "Server CPU at 95%" --type alert

# Check trigger fired
vigil status
```

### MCP Server Alerts → Slack

Route MCPWatch alerts (tool errors, latency spikes) to Slack:

```bash
# Via CLI
vigil triggers --action add \
  --name "mcp-errors-to-slack" \
  --signal_type "alert" \
  --agent_pattern "mcpwatch/*" \
  --action_type "webhook" \
  --action_config '{"url":"https://hooks.slack.com/services/T.../B.../xxx","method":"POST","template":{"text":":warning: MCP Alert: {content}"}}'
```

```python
# Via Python
triggers.create(
    name="mcp-errors-to-slack",
    signal_type="alert",
    agent_pattern="mcpwatch/*",
    action_type="webhook",
    action_config={
        "url": "https://hooks.slack.com/services/T.../B.../xxx",
        "method": "POST",
        "template": {
            "text": ":warning: MCP Alert: {content}"
        }
    },
)
```

MCPWatch emits alerts as agent `mcpwatch/<server-name>` — the glob pattern `mcpwatch/*` catches all servers.

## Trigger Patterns

| Pattern | Matches |
|---------|---------|
| `agent_pattern="*"` | All agents |
| `agent_pattern="backend-*"` | Agents starting with "backend-" |
| `content_pattern=".*error.*"` | Signals containing "error" |
| `signal_type="alert"` | Only alert-type signals |

## What It Looks Like in Slack

```
Vigil Alert from backend-agent: Database connection pool exhausted (12/12 active)
```

```
Deploy: Deployed to production successfully
```
