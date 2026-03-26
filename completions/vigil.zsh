#compdef vigil
# Zsh completion for vigil CLI
# Install: copy to a directory in your $fpath (e.g., ~/.zsh/completions/)
# Then add to .zshrc: fpath=(~/.zsh/completions $fpath) && autoload -Uz compinit && compinit

_vigil() {
    local -a commands
    commands=(
        'init:Initialize a new Vigil project'
        'daemon:Manage the awareness daemon'
        'serve:Start the Vigil MCP server'
        'signal:Emit a signal'
        'status:Show current awareness'
        'frames:List registered frames'
        'tools:List registered tools'
        'boot:Show compiled hot context'
        'handoff:Write a structured session handoff'
        'resume:Resume from last handoff'
        'history:Browse compacted signal history'
        'agents:List known agents'
        'compact:Run signal compaction manually'
        'version:Show Vigil version'
        'doctor:Diagnose common issues'
        'know:Store a knowledge entry'
        'recall:Fuzzy-search knowledge'
        'knowledge:List all knowledge entries'
        'forget:Delete a knowledge entry'
        'quickstart:Interactive setup wizard'
        'extract:Auto-extract knowledge from signal patterns'
        'export:Export awareness state to markdown'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe -t commands 'vigil command' commands
            ;;
        args)
            case $words[1] in
                daemon)
                    local -a daemon_commands
                    daemon_commands=(
                        'start:Start the daemon'
                        'status:Check daemon status'
                    )
                    _arguments -C \
                        '1:subcommand:->subcmd' \
                        '*::arg:->subargs'
                    case $state in
                        subcmd)
                            _describe -t commands 'daemon command' daemon_commands
                            ;;
                        subargs)
                            case $words[1] in
                                start)
                                    _arguments \
                                        '--interval[Compile interval in seconds]:seconds:(30 60 90 120)' \
                                        '--output[Path to write AWARENESS.md]:file:_files'
                                    ;;
                            esac
                            ;;
                    esac
                    ;;
                init)
                    _arguments \
                        '--force[Reinitialize existing database]'
                    ;;
                serve)
                    _arguments \
                        '--transport[Transport protocol]:transport:(stdio sse http)' \
                        '--host[Server host]:host:' \
                        '--port[Server port]:port:'
                    ;;
                signal)
                    _arguments \
                        '1:agent:' \
                        '2:message:' \
                        '--type[Signal type]:type:(observation handoff summary alert)'
                    ;;
                tools)
                    _arguments \
                        '--frame[Filter by frame]:frame:'
                    ;;
                boot)
                    _arguments \
                        '--json[Output as JSON]'
                    ;;
                handoff)
                    _arguments \
                        '1:agent:' \
                        '2:summary:' \
                        '--files[Comma-separated files touched]:files:' \
                        '--decisions[Comma-separated decisions]:decisions:' \
                        '--next-steps[Comma-separated next steps]:steps:'
                    ;;
                resume)
                    _arguments \
                        '1:agent:'
                    ;;
                history)
                    _arguments \
                        '--days[Days to look back]:days:' \
                        '--agent[Filter by agent]:agent:'
                    ;;
                compact)
                    _arguments \
                        '--dry-run[Preview without modifying data]'
                    ;;
                know)
                    _arguments \
                        '1:key:' \
                        '2:value:' \
                        '--category[Category]:category:' \
                        '--agent[Source agent]:agent:' \
                        '--confidence[Confidence 0.0-1.0]:confidence:'
                    ;;
                recall)
                    _arguments \
                        '1:query:' \
                        '--category[Filter by category]:category:' \
                        '--limit[Max results]:limit:'
                    ;;
                knowledge)
                    _arguments \
                        '--category[Filter by category]:category:' \
                        '--limit[Max entries]:limit:'
                    ;;
                forget)
                    _arguments \
                        '1:key:'
                    ;;
                extract)
                    _arguments \
                        '--days[Days of signals to analyze]:days:' \
                        '--dry-run[Show suggestions without storing]'
                    ;;
                export)
                    _arguments \
                        '(-o --output)'{-o,--output}'[Write to file]:file:_files' \
                        '--hours[Hours of signal history]:hours:'
                    ;;
            esac
            ;;
    esac
}

_vigil
