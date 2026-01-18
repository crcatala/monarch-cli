---
id: mc-fa92
status: open
deps: [mc-6a5b]
links: []
created: 2026-01-18T15:59:30Z
type: task
priority: 0
assignee: cc-vps
parent: mc-96b1
tags: [phase-0, setup, structure]
---
# Project Directory Structure

Create the complete project directory structure following Python src-layout conventions.

## Directory Structure
```
monarch-cli/
├── src/
│   └── monarch_cli/
│       ├── __init__.py          # Package init, exports __version__
│       ├── py.typed             # Marker for type hints (empty file)
│       ├── main.py              # Typer app entry point
│       ├── commands/            # CLI command handlers (thin)
│       │   └── __init__.py
│       ├── core/                # Infrastructure
│       │   └── __init__.py
│       ├── services/            # Business logic layer
│       │   └── __init__.py
│       ├── transformers/        # API response → CLI output
│       │   └── __init__.py
│       └── output/              # Output formatting
│           └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   └── live/                    # Real API tests (local dev only)
│       └── __init__.py
├── scripts/                     # Verification and utility scripts
├── .github/
│   └── workflows/
│       └── ci.yml
└── .vscode/                     # Editor settings
    └── settings.json
```

## Package __init__.py Files
All `__init__.py` files should be minimal:
- `src/monarch_cli/__init__.py`: Only exports `__version__ = "0.1.0"`
- Other `__init__.py` files: Empty (use explicit imports)

## py.typed Marker
Create empty `src/monarch_cli/py.typed` file to indicate the package supports type hints. Required for mypy type checking to work correctly with the package.

## Design Rationale
- **commands/**: Thin handlers that parse CLI args and delegate to services
- **core/**: Infrastructure code (adapter, session, exceptions, retry, dates)
- **services/**: Business logic, orchestration, retries, error mapping
- **transformers/**: Data transformation from API responses to CLI schemas
- **output/**: Formatting (JSON, table, CSV) and progress indicators

## Acceptance Criteria

- [ ] All directories created under src/monarch_cli/
- [ ] All __init__.py files present (minimal content)
- [ ] py.typed marker file created
- [ ] tests/ directory with conftest.py stub
- [ ] tests/live/ directory for live API tests
- [ ] scripts/ directory for verification scripts
- [ ] .github/workflows/ directory exists
- [ ] .vscode/settings.json with Python/Ruff config

