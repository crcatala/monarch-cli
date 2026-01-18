# Phase 0: Project Setup - Progress Log

This file tracks completed work and patterns learned during this loop.

---

## Codebase Patterns

- **uv init --lib**: Creates src-layout with `src/<package>/` directory structure automatically
- **Pre-commit check**: Ruff not available until dev dependencies are added in task 2

---

## Completed Tasks

## [2026-01-18 08:41] - Repository Initialization (mc-99cb)
- Initialized project with `uv init --lib --name monarch-cli`
- Updated requires-python to >=3.12 (uv defaults to >=3.13)
- Created comprehensive .gitignore covering Python, venvs, dist, testing, IDEs, OS files
- Updated README.md with project description and basic usage info
- Files changed: pyproject.toml, .gitignore, README.md, src/monarch_cli/__init__.py
- **Learnings:** `uv init --lib` sets requires-python to current Python version (3.13), need to manually adjust if targeting older versions

---

## Issues Encountered

(recorded as tasks complete)

## [2026-01-18 08:42] - pyproject.toml Configuration (mc-6a5b)
- Added complete [project] metadata with description
- Added runtime dependencies: typer[all], monarchmoneycommunity, keyring, rich, platformdirs, httpx
- Added dev dependencies in [project.optional-dependencies]: pytest, pytest-asyncio, pytest-cov, ruff, mypy
- Added entry point: monarch = 'monarch_cli.main:app'
- Configured [tool.ruff] with target-version py312, line-length 100, linting rules
- Configured [tool.mypy] with strict=true
- Configured [tool.pytest.ini_options] with testpaths and asyncio_mode
- Files changed: pyproject.toml
- **Learnings:** typer[all] extra is deprecated in typer 0.21.1+, but still works as a no-op. uv sync --all-extras installs both runtime and optional dependencies.

---
