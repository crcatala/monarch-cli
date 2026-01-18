---
id: mc-e04c
status: open
deps: [mc-52c3]
links: []
created: 2026-01-18T16:10:46Z
type: task
priority: 1
assignee: cc-vps
parent: mc-1568
tags: [phase-5, release, checklist]
---
# Release Readiness Checklist (v1.0)

Complete pre-release checklist before publishing to PyPI.

## P0: Must Fix Before PyPI Publish

### 1. Add LICENSE File (MIT)
- [ ] Create LICENSE file with MIT license text
- [ ] Add year and author name
- [ ] Verify pyproject.toml license field matches

### 2. Verify Package Contents
Create/update `MANIFEST.in` if needed:
```
include LICENSE
include README.md
include CHANGELOG.md
recursive-include src/monarch_cli py.typed
```

### 3. Verify Package Metadata
Check pyproject.toml:
- [ ] name is available on PyPI
- [ ] version is 0.1.0 (or appropriate)
- [ ] description is clear and concise
- [ ] README renders correctly (PyPI uses README for description)
- [ ] classifiers are accurate
- [ ] URLs point to correct repos

### 4. Test Build
```bash
uv build
ls dist/  # Should have .whl and .tar.gz

# Test install in clean environment
uv venv test-install
source test-install/bin/activate
uv pip install dist/monarch_cli-0.1.0-py3-none-any.whl
monarch --version
deactivate
rm -rf test-install
```

### 5. Verify Entry Point
```bash
# After test install:
monarch --help
monarch auth --help
monarch accounts --help
```

### 6. CI Passing
- [ ] All GitHub Actions workflows green
- [ ] No lint warnings
- [ ] No type errors
- [ ] Tests passing with coverage >70%

## P1: Strongly Recommended

### 7. Check PyPI Name Availability
```bash
# Check if name is taken
curl https://pypi.org/pypi/monarch-cli/json
# 404 = available, 200 = taken
```

Fallback names if taken:
- monarch-money-cli
- mm-cli

### 8. Test on TestPyPI First
```bash
uv publish --repository testpypi
pip install --index-url https://test.pypi.org/simple/ monarch-cli
```

### 9. Tag Release
```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

## Publishing
```bash
# Build
uv build

# Publish to PyPI
uv publish  # Will prompt for PyPI credentials/token
```

## Post-Release
- [ ] Verify installation works: `pip install monarch-cli`
- [ ] Create GitHub release with changelog
- [ ] Announce release (if applicable)

## Acceptance Criteria

- [ ] LICENSE file present and correct
- [ ] Package builds without errors
- [ ] Package installs in clean environment
- [ ] Entry point works after install
- [ ] CI is green
- [ ] PyPI name is available or fallback chosen
- [ ] TestPyPI upload successful
- [ ] Version tag created


## Notes

**2026-01-18T16:17:37Z**

## 🔴 HUMAN CHECKPOINT - Release Decision

This ticket requires human intervention for:

1. **PyPI Token** - Agent cannot publish without credentials
2. **Name Availability** - Human decides fallback if monarch-cli taken
3. **Go/No-Go** - Final approval to publish publicly

**Agent can prepare everything**:
- Build package
- Test install in clean venv
- Upload to TestPyPI (if token provided)
- Generate release notes

**Human must**:
- Provide PyPI token (or set PYPI_TOKEN env var)
- Make final publish decision
- Create GitHub release
