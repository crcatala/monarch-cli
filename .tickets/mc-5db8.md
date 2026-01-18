---
id: mc-5db8
status: open
deps: [mc-c802]
links: []
created: 2026-01-18T22:27:49Z
type: task
priority: 2
assignee: cc-vps
parent: mc-0ed9
---
# Upload to TestPyPI and verify installation

Upload package to TestPyPI using 'twine upload --repository testpypi dist/*'. Then test installation in fresh venv with pip install from TestPyPI. Requires ~/.pypirc configured with TestPyPI token (human prerequisite).

## Acceptance Criteria

Package uploaded to TestPyPI successfully
Package installable from TestPyPI
monarch --version works after TestPyPI install

