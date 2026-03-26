# Bash completion for vigil CLI
# Install: source this file, or copy to /etc/bash_completion.d/vigil

_vigil() {
    local cur prev commands daemon_commands signal_types transports
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    commands="init daemon serve signal status frames tools boot handoff resume history agents compact version doctor know recall knowledge forget quickstart extract export"
    daemon_commands="start status"
    signal_types="observation handoff summary alert"
    transports="stdio sse http"

    # Top-level commands
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
        return 0
    fi

    # Subcommands and flags
    case "${COMP_WORDS[1]}" in
        daemon)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "${daemon_commands}" -- "${cur}") )
            elif [[ "${COMP_WORDS[2]}" == "start" ]]; then
                COMPREPLY=( $(compgen -W "--interval --output" -- "${cur}") )
            fi
            ;;
        init)
            COMPREPLY=( $(compgen -W "--force" -- "${cur}") )
            ;;
        serve)
            case "${prev}" in
                --transport)
                    COMPREPLY=( $(compgen -W "${transports}" -- "${cur}") )
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "--transport --host --port" -- "${cur}") )
                    ;;
            esac
            ;;
        signal)
            if [[ "${prev}" == "--type" ]]; then
                COMPREPLY=( $(compgen -W "${signal_types}" -- "${cur}") )
            elif [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--type" -- "${cur}") )
            fi
            ;;
        tools)
            COMPREPLY=( $(compgen -W "--frame" -- "${cur}") )
            ;;
        boot)
            COMPREPLY=( $(compgen -W "--json" -- "${cur}") )
            ;;
        handoff)
            COMPREPLY=( $(compgen -W "--files --decisions --next-steps" -- "${cur}") )
            ;;
        history)
            COMPREPLY=( $(compgen -W "--days --agent" -- "${cur}") )
            ;;
        compact)
            COMPREPLY=( $(compgen -W "--dry-run" -- "${cur}") )
            ;;
        know)
            COMPREPLY=( $(compgen -W "--category --agent --confidence" -- "${cur}") )
            ;;
        recall)
            COMPREPLY=( $(compgen -W "--category --limit" -- "${cur}") )
            ;;
        knowledge)
            COMPREPLY=( $(compgen -W "--category --limit" -- "${cur}") )
            ;;
        extract)
            COMPREPLY=( $(compgen -W "--days --dry-run" -- "${cur}") )
            ;;
        export)
            COMPREPLY=( $(compgen -W "--output --hours" -- "${cur}") )
            ;;
    esac

    return 0
}

complete -F _vigil vigil
