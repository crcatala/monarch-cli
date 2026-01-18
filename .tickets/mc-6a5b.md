---
id: mc-6a5b
status: open
deps: [mc-99cb]
links: []
created: 2026-01-18T15:59:14Z
type: task
priority: 0
assignee: cc-vps
parent: mc-96b1
tags: [phase-0, setup, config]
---
# pyproject.toml Configuration

Create comprehensive pyproject.toml with all project configuration.

## Project Metadata
- name: monarch-cli
- version: 0.1.0
- description: CLI for Monarch Money - AI agent friendly financial data access
- Python requirement: >=3.12
- License: MIT

## Runtime Dependencies
- typer[all]>=0.9.0 (CLI framework with rich integration)
- monarchmoneycommunity>=1.0.0 (API client - import as `monarchmoney`)
- keyring>=24.0.0 (OS credential storage)
- rich>=13.0.0 (Terminal formatting)
- platformdirs>=4.0.0 (XDG/cross-platform paths)
- httpx>=0.27.0 (For retry/timeout handling)

## Dev Dependencies
- pytest>=8.0.0
- pytest-asyncio>=0.23.0
- pytest-cov>=4.0.0
- ruff>=0.4.0
- mypy>=1.10.0

## Entry Point
```toml
[project.scripts]
monarch = "monarch_cli.main:app"
```

## Tool Configurations to Include
1. **Ruff**: target-version py312, line-length 100, select E/W/F/I/B/C4/UP/ARG/SIM
2. **mypy**: strict mode, ignore_missing_imports for monarchmoney/keyring
3. **pytest**: testpaths=["tests"], asyncio_mode="auto", live test markers
4. **coverage**: source src/monarch_cli, fail_under=70

## Important Notes
- Install `monarchmoneycommunity` from PyPI but import as `monarchmoney`
- All tool config goes in pyproject.toml (single source of truth)
- Use setuptools build backend for simplicity

## Acceptance Criteria

- [ ] All runtime dependencies specified with version constraints
- [ ] All dev dependencies in optional-dependencies
- [ ] Entry point `monarch = monarch_cli.main:app` defined
- [ ] Ruff config complete with lint rules and format settings
- [ ] mypy config with strict mode and ignore_missing_imports
- [ ] pytest config with asyncio_mode and live test markers
- [ ] Coverage config with fail_under threshold
- [ ] Keywords and classifiers for PyPI discovery

