# Shell Completions

Tab completion for the `vigil` CLI.

## Bash

```bash
# Option 1: Source directly (current session only)
source completions/vigil.bash

# Option 2: Install system-wide
sudo cp completions/vigil.bash /etc/bash_completion.d/vigil
```

## Zsh

```bash
# Option 1: Copy to your fpath
mkdir -p ~/.zsh/completions
cp completions/vigil.zsh ~/.zsh/completions/_vigil

# Add to your .zshrc (if not already there):
# fpath=(~/.zsh/completions $fpath)
# autoload -Uz compinit && compinit

# Option 2: Oh My Zsh
cp completions/vigil.zsh ~/.oh-my-zsh/completions/_vigil
```

## What Completes

- All 21 top-level commands
- `daemon start|status` subcommands
- Flag names and values for every command
- Signal types: `observation`, `handoff`, `summary`, `alert`
- Transport modes: `stdio`, `sse`, `http`
- File path completion where applicable
