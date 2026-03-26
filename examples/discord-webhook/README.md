# Vigil + Discord

Route Vigil signals to Discord channels using event triggers and Discord webhooks.

## Setup

### 1. Create a Discord Webhook

1. Open your Discord server settings
2. Go to **Integrations** > **Webhooks**
3. Click **New Webhook**, pick a channel, and copy the URL

### 2. Create a Vigil Trigger

```python
from vigil import VigilDB, TriggerManager

db = VigilDB("vigil.db")
triggers = TriggerManager(db)

# All alerts → Discord
triggers.create(
    name="alerts-to-discord",
    signal_type="alert",
    agent_pattern="*",
    action_type="webhook",
    action_config={
        "url": "https://discord.com/api/webhooks/1234.../abcd...",
        "method": "POST",
        "template": {
            "content": "**Vigil Alert** [{agent}]: {content}"
        }
    },
)

# Handoff summaries → Discord (keep your team informed)
triggers.create(
    name="handoffs-to-discord",
    signal_type="handoff",
    agent_pattern="*",
    action_type="webhook",
    action_config={
        "url": "https://discord.com/api/webhooks/1234.../abcd...",
        "method": "POST",
        "template": {
            "content": "**Session Handoff** [{agent}]: {content}"
        }
    },
)
```

### 3. Test It

```bash
vigil signal test-agent "Build failed on main" --type alert
```

You should see a message in your Discord channel within seconds.

## Discord Embed Format

For richer messages, use Discord's embed format in the template:

```python
triggers.create(
    name="alerts-to-discord-rich",
    signal_type="alert",
    agent_pattern="*",
    action_type="webhook",
    action_config={
        "url": "https://discord.com/api/webhooks/...",
        "method": "POST",
        "template": {
            "embeds": [{
                "title": "Vigil Alert",
                "description": "{content}",
                "color": 15158332,
                "fields": [
                    {"name": "Agent", "value": "{agent}", "inline": True},
                    {"name": "Type", "value": "{signal_type}", "inline": True}
                ]
            }]
        }
    },
)
```
