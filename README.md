# Monarch CLI

A Python CLI wrapper around `monarchmoneycommunity` for AI agent integration with Monarch Money financial data.

## Overview

Monarch CLI provides a command-line interface for interacting with Monarch Money, designed specifically for AI agent workflows. It enables automated financial data retrieval and analysis.

## Requirements

- Python 3.12+
- A Monarch Money account

## Installation

```bash
# Full setup (syncs dependencies + installs git hooks)
make setup

# Or manually:
uv sync --all-extras
uv run prek install
```

## Development

Git hooks are managed with [prek](https://github.com/j178/prek) (a fast pre-commit alternative).

- **Pre-push hook**: Runs `make verify` (format check, lint, typecheck, tests) before pushing
- Hooks are installed automatically via `make setup`
- Run `uv run prek run --hook-stage pre-push` to test the hook manually

## Usage

```bash
monarch --help
```

## Shell Completions

Monarch CLI supports tab completion for commands, options, and arguments. Enable completions for your shell:

### Bash

```bash
monarch --install-completion bash
```

Then restart your shell or source your `~/.bashrc`:

```bash
source ~/.bashrc
```

### Zsh

```bash
monarch --install-completion zsh
```

Then restart your shell or source your `~/.zshrc`:

```bash
source ~/.zshrc
```

### Fish

```bash
monarch --install-completion fish
```

Then restart your shell or source the completions:

```bash
source ~/.config/fish/completions/monarch.fish
```

### Verifying Completions

After installation, try typing `monarch ` and pressing Tab to see available commands:

```bash
monarch <TAB>
# Shows: accounts  auth  budgets  cashflow  categories  transactions
```
