# LinkedIn Post — Vigil v2.2

I built Vigil because my AI agents kept starting every session from zero.

95 tools, 6 different interfaces, multiple agents working on trading, coding, and creative writing. Every new session meant: "remind me what we were working on." Tool definitions alone burned 50K+ tokens before the agent did anything useful. And when MCP servers failed silently? Nobody knew for days.

Vigil gives agents a nervous system:

- Awareness daemon compiles system state every 90s — agents boot in <1 second with full context
- Frame-based tool filtering cuts tool-definition tokens by 75-85%
- Signal protocol lets agents coordinate without talking directly
- Session handoff means work picks up exactly where it left off
- MCPWatch: one-line instrumentation for any MCP server — tracks latency, errors, silent failures
- WebSocket real-time signal streaming + analytics dashboard
- Hosted cloud tier at app.vigil-agent.com (GitHub OAuth, free tier included)

v2.2 on PyPI: pip install vigil-agent
14 modules. 311 tests. 8,400+ lines. MIT license. Zero dependencies.

Integration examples for Claude Code, Cursor, Claude Desktop, GitHub Actions, Slack, and Discord.

The existing tools (Mem0, Letta, LangGraph) solve memory and orchestration. Nobody was solving awareness — what's happening right now across your agents. That's the gap Vigil fills.

Now with a hosted cloud tier: sign up with GitHub, connect your agents, monitor everything from one dashboard. Free for small projects.

GitHub: https://github.com/AlexlaGuardia/Vigil
Cloud: https://app.vigil-agent.com
Landing: https://vigil-agent.com

#AI #Python #OpenSource #MCP #AIAgents #DeveloperTools #MCPWatch
