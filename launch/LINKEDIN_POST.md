# LinkedIn Post — Vigil v1.5.1 Launch

I built Vigil because my AI agents kept starting every session from zero.

95 tools, 6 different interfaces, multiple agents working on trading, coding, and creative writing. Every new session meant: "remind me what we were working on." Tool definitions alone burned 50K+ tokens before the agent did anything useful.

Vigil gives agents a nervous system:

- Awareness daemon compiles system state every 90s — agents boot in <1 second with full context
- Frame-based tool filtering cuts tool-definition tokens by 75-85% (backend mode shows 14 tools, not 95)
- Signal protocol lets agents coordinate without talking directly
- Session handoff means work picks up exactly where it left off
- Knowledge auto-extract watches signal patterns and surfaces recurring themes automatically
- Built-in MCP server for Claude Code, Cursor, and Claude Desktop

v1.5.1 is on PyPI: pip install vigil-agent
14 modules. 268 tests. 7,500+ lines. MIT license. Zero dependencies.

Ready-to-use integration examples for Claude Code, Cursor, Claude Desktop, GitHub Actions, Slack, and Discord. Tab completion for bash/zsh.

The existing tools (Mem0, Letta, LangGraph) solve memory and orchestration. Nobody was solving awareness — a continuously-compiled understanding of what's happening right now. That's the gap Vigil fills.

GitHub: https://github.com/AlexlaGuardia/Vigil
PyPI: https://pypi.org/project/vigil-agent/

I also wrote about the architecture:
https://dev.to/alexlaguardia/i-built-a-nervous-system-for-ai-agents-not-another-memory-store-5a8a

#AI #Python #OpenSource #MCP #AIAgents #DeveloperTools
