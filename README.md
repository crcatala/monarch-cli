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
