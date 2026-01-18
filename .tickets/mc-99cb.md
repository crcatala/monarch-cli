---
id: mc-99cb
status: open
deps: []
links: []
created: 2026-01-18T15:59:00Z
type: task
priority: 0
assignee: cc-vps
parent: mc-96b1
tags: [phase-0, setup]
---
# Repository Initialization

Initialize the Monarch CLI repository with proper Python project structure.

## Tasks
1. Create new repository: `monarch-cli`
2. Initialize with `uv init`
3. Set Python 3.12+ as minimum version
4. Add comprehensive `.gitignore` for Python projects
5. Create initial README.md with project description

## Technical Notes
- Use `uv init --lib` for library/application structure
- The `.gitignore` should cover:
  - Python artifacts (__pycache__, *.pyc, *.pyo)
  - Virtual environments (.venv, venv)
  - Build artifacts (dist/, build/, *.egg-info)
  - IDE files (.vscode/, .idea/)
  - Test artifacts (.pytest_cache/, .coverage, htmlcov/)
  - mypy cache (.mypy_cache/)
  - OS files (.DS_Store)

## Why src-layout?
- Prevents `import monarch_cli` from accidentally importing local folder instead of installed package
- Required for proper editable installs (`uv pip install -e .`)
- Industry standard for publishable packages

## Acceptance Criteria

- [ ] Repository created with proper name
- [ ] `uv init --lib` or equivalent completed
- [ ] Python 3.12+ specified as minimum
- [ ] .gitignore includes all necessary patterns
- [ ] README.md has basic project description

