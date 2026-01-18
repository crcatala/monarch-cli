---
id: mc-a77b
status: open
deps: []
links: []
created: 2026-01-18T22:27:36Z
type: task
priority: 2
assignee: cc-vps
parent: mc-0ed9
---
# Add twine to dev dependencies

Add twine>=5.0.0 to [project.optional-dependencies] dev list in pyproject.toml, then run 'uv sync --all-extras' to update lock file.

## Acceptance Criteria

twine is in pyproject.toml dev dependencies
uv.lock is updated
'uv run twine --version' works

