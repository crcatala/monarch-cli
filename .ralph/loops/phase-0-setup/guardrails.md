# Phase 0 Guardrails

## Project Standards

1. **Python Version**: 3.12+ required. Use modern syntax (match statements, type hints, etc.)

2. **Package Layout**: Use src-layout (`src/monarch_cli/`). Never put source code directly in project root.

3. **All Config in pyproject.toml**: No separate setup.py, setup.cfg, .flake8, .isort.cfg, etc. Everything goes in pyproject.toml.

4. **Use uv**: All Python commands should use `uv run`. Don't activate venvs manually.

5. **Imports**: The `monarchmoneycommunity` package is imported as `monarchmoney`:
   ```python
   from monarchmoney import MonarchMoney
   ```

## Code Style

- Line length: 100 characters
- Quotes: Double quotes for strings
- Imports: Sorted by ruff (isort rules)
- Type hints: Required on all public functions

## Commit Standards

- One logical change per commit
- Commit message format: `phase-0: <description>`
- Run `make verify` before committing

## Reference Documents

- Main plan: `plans/monarch-cli-implementation-plan.md`
- Tickets: `.tickets/mc-*.md`
