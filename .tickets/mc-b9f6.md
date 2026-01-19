---
id: mc-b9f6
status: closed
deps: []
links: []
created: 2026-01-18T22:28:20Z
type: task
priority: 2
assignee: cc-vps
parent: mc-0ed9
---
# Create PyPI publish GitHub Actions workflow

Create .github/workflows/publish.yml triggered on release published. Uses uv, runs quality checks, builds package, validates with twine, publishes via pypa/gh-action-pypi-publish with trusted publishing (id-token: write). Use template from plans/RELEASE-READINESS-v0.1.0.md.

## Acceptance Criteria

.github/workflows/publish.yml exists
Triggers on release published
Runs quality checks before publish
Uses trusted publishing (id-token permission)
Uses pypa/gh-action-pypi-publish action


## Notes

**2026-01-19T00:53:59Z**

Workflow created but later removed in favor of manual publishing via 'make prepublish' + twine. See docs/RELEASING.md.
