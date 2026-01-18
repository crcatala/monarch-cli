# Release Readiness Plan v0.1.0

> **The authoritative checklist for the 0.1.0 open source release.**
>
> Adapted from [raindrop-cli release plan](https://github.com/crcatala/raindrop-cli-spike/blob/main/plans/RELEASE-READINESS-v0.1.0.md) for Python ecosystem.
>
> **Created:** January 18, 2026

---

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CHECKPOINT 0: Prerequisites (Human Required)                               │
│  └─ Fill in: GITHUB_OWNER, AUTHOR_NAME, AUTHOR_EMAIL, PyPI accounts        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Phase 1: P0 Items (Agent Automatable)                                      │
│  └─ Fix URLs, metadata, build verification, TestPyPI upload                │
├─────────────────────────────────────────────────────────────────────────────┤
│  CHECKPOINT 1: Verify TestPyPI (Human Required)                             │
│  └─ Install from TestPyPI, test CLI manually, verify package page          │
├─────────────────────────────────────────────────────────────────────────────┤
│  Phase 2: P1 Items (Agent Automatable)                                      │
│  └─ Community files, issue templates, publish workflow, Makefile           │
├─────────────────────────────────────────────────────────────────────────────┤
│  CHECKPOINT 2: Pre-Publish Review (Human Required)                          │
│  └─ Final review, then human runs: twine upload dist/*                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Executive Summary

**The codebase is in excellent shape.** The gap is mostly in OSS documentation and metadata polish.

| Aspect | Score | Notes |
|--------|-------|-------|
| Architecture | 9/10 | Clean separation, well-organized modules |
| Code Quality | 9/10 | Strict mypy, comprehensive linting |
| Test Coverage | 91% | 484 tests passing, good coverage |
| CLI UX | 9/10 | Great help, TTY detection, multiple formats |
| Security | 9/10 | Secure token storage, no secrets in code |
| Documentation | 8/10 | Comprehensive README, needs URL fixes |
| **OSS Readiness** | **6/10** | Missing community files, metadata gaps |

**Estimated time to release-ready: ~1.5-2 hours of focused work.**

---

## 🛑 CHECKPOINT 0: Prerequisites (Human Decisions Required)

**STOP. An agent cannot proceed without these decisions from the maintainer.**

| Decision | Current Value | Options |
|----------|---------------|---------|
| **GitHub username/org** | `yourusername` (placeholder) | What GitHub account will host this repo? |
| **Author name** | `cc-vps` | Real name, pseudonym, or keep as-is? |
| **Author email** | `crcatala+vps@gmail.com` | Public contact email for PyPI/security reports |
| **PyPI account** | None | Need account at pypi.org and test.pypi.org |

**Once decided, set these values:**
```bash
# Example - replace with actual values
GITHUB_OWNER="crcatala"           # or org name
GITHUB_REPO="monarch-cli"
AUTHOR_NAME="Christian Catalan"   # or pseudonym
AUTHOR_EMAIL="your@email.com"
```

These values are used throughout this plan as `${GITHUB_OWNER}`, etc.

---

## What's Already Done ✅

These items are complete and well-implemented:

- ✅ `LICENSE` file (MIT)
- ✅ `CHANGELOG.md` following Keep a Changelog format
- ✅ Comprehensive `README.md` (renders correctly for PyPI)
- ✅ `py.typed` marker for PEP 561 type checking
- ✅ CI workflow with lint, typecheck, test
- ✅ `Makefile` with `verify` target
- ✅ Version sourced from `__init__.py`
- ✅ Good `.gitignore`
- ✅ Pre-commit hooks (via prek)
- ✅ 91% test coverage
- ✅ Multiple output formats (JSON, table, CSV, etc.)
- ✅ AI-agent friendly design
- ✅ Package name `monarch-cli` is available on PyPI (verified 2026-01-18)

---

## 🔴 P0: Must Fix Before PyPI Publish

These are **release blockers**. Do not publish without completing all P0 items.

### 1. Fix All Placeholder URLs ⏱️ 5 min

**Dependency:** Requires `GITHUB_OWNER` decision from Prerequisites.

Repository URLs contain `yourusername` placeholder in multiple files. Fix all at once:

**README.md** (line ~372):
```markdown
# Change from:
git clone https://github.com/yourusername/monarch-cli.git
# Change to:
git clone https://github.com/${GITHUB_OWNER}/monarch-cli.git
```

**CHANGELOG.md** (lines 83-84):
```markdown
# Change from:
[Unreleased]: https://github.com/yourusername/monarch-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/monarch-cli/releases/tag/v0.1.0
# Change to:
[Unreleased]: https://github.com/${GITHUB_OWNER}/monarch-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/${GITHUB_OWNER}/monarch-cli/releases/tag/v0.1.0
```

**Verification:**
```bash
grep -rn "yourusername" . --include="*.md" --include="*.toml"
# Should return no results
```

---

### 2. Update Author Information ⏱️ 3 min

**Dependency:** Requires `AUTHOR_NAME` and `AUTHOR_EMAIL` decisions from Prerequisites.

**pyproject.toml:**
```toml
authors = [
    { name = "${AUTHOR_NAME}", email = "${AUTHOR_EMAIL}" }
]
```

**LICENSE** (line 3):
```
Copyright (c) 2026 ${AUTHOR_NAME}
```

---

### 3. Add PyPI Metadata to pyproject.toml ⏱️ 5 min

**Dependency:** Requires `GITHUB_OWNER` decision from Prerequisites.

Add these sections to `pyproject.toml` after the existing `[project]` fields:

```toml
[project]
# ... existing fields (name, version, description, etc.) ...

# ADD these new fields:
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Office/Business :: Financial",
    "Topic :: Utilities",
    "Typing :: Typed",
]
keywords = ["monarch", "money", "finance", "cli", "personal-finance", "budgeting"]

[project.urls]
Homepage = "https://github.com/${GITHUB_OWNER}/monarch-cli"
Documentation = "https://github.com/${GITHUB_OWNER}/monarch-cli#readme"
Repository = "https://github.com/${GITHUB_OWNER}/monarch-cli"
Issues = "https://github.com/${GITHUB_OWNER}/monarch-cli/issues"
Changelog = "https://github.com/${GITHUB_OWNER}/monarch-cli/blob/main/CHANGELOG.md"
```

**Insert location:** After `requires-python` line, before `dependencies`.

---

### 4. Add twine to Dev Dependencies ⏱️ 2 min

Add `twine` to dev dependencies for package validation:

**pyproject.toml** - add to `[project.optional-dependencies]` dev list:
```toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "twine>=5.0.0",
]
```

Then sync:
```bash
uv sync --all-extras
```

---

### 5. Verify Build Artifacts ⏱️ 5 min

Run these commands and verify each step passes:

```bash
# Clean and rebuild
rm -rf dist/ build/ *.egg-info
uv build

# Check wheel contents - should see all source files
unzip -l dist/*.whl

# Verify LICENSE is included in metadata
unzip -p dist/*.whl 'monarch_cli-*/METADATA' | grep -A2 "License"
# Expected: Should show MIT license info

# Verify entry point works from built package
pip install dist/*.whl --force-reinstall
monarch --version   # Should print: monarch-cli 0.1.0
monarch --help      # Should show help text
monarch auth --help # Should show auth subcommands
```

---

### 6. Test on TestPyPI ⏱️ 15 min

**Dependency:** Requires PyPI account from Prerequisites.

#### 6a. Create TestPyPI Account and Token

1. Go to https://test.pypi.org/account/register/
2. Create account and verify email
3. Go to https://test.pypi.org/manage/account/token/
4. Create API token with scope "Entire account"
5. Save token (starts with `pypi-`)

#### 6b. Configure twine

Create `~/.pypirc` (if it doesn't exist):
```ini
[testpypi]
  username = __token__
  password = pypi-YOUR_TEST_PYPI_TOKEN_HERE
```

**Security:** Set permissions: `chmod 600 ~/.pypirc`

#### 6c. Upload and Test

```bash
# Upload to TestPyPI
uv run twine upload --repository testpypi dist/*

# Test installation in a fresh environment
python -m venv /tmp/test-monarch
source /tmp/test-monarch/bin/activate
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ monarch-cli

# Verify
monarch --version
monarch --help

# Cleanup
deactivate
rm -rf /tmp/test-monarch
```

**Note:** The `--extra-index-url` is needed because TestPyPI doesn't have all dependencies.

---

## 🛑 CHECKPOINT 1: Verify TestPyPI Installation

**STOP HERE.** Human verification required before proceeding.

### What to Verify

1. **Package page looks correct:**
   - Go to `https://test.pypi.org/project/monarch-cli/`
   - README renders properly
   - Metadata (author, license, links) displays correctly
   - Classifiers show up in sidebar

2. **Installation works:**
   ```bash
   # Fresh environment
   python -m venv /tmp/monarch-verify
   source /tmp/monarch-verify/bin/activate
   pip install --index-url https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ monarch-cli
   ```

3. **CLI functions correctly:**
   ```bash
   monarch --version          # Shows 0.1.0
   monarch --help             # Shows all commands
   monarch auth status        # Runs without crashing
   monarch auth doctor        # Shows diagnostic info
   ```

4. **Cleanup:**
   ```bash
   deactivate
   rm -rf /tmp/monarch-verify
   ```

### ✅ Checkpoint Complete When

- [ ] Package page renders correctly on TestPyPI
- [ ] CLI installs and runs without errors
- [ ] Human approves proceeding to P1 items

---

## 🟠 P1: Strongly Recommended

Complete these for a polished first impression. Can be done same day as P0.

### 7. Add CONTRIBUTING.md ⏱️ 10 min

**Dependency:** Requires `GITHUB_OWNER` decision from Prerequisites.

Create `CONTRIBUTING.md` in repo root:

```markdown
# Contributing to Monarch CLI

Thank you for considering contributing!

## Development Setup

```bash
git clone https://github.com/${GITHUB_OWNER}/monarch-cli.git
cd monarch-cli
make setup
```

## Development Workflow

```bash
make verify      # Run all checks (format, lint, typecheck, test)
make format      # Auto-format code
make lint-fix    # Fix linting issues
make test        # Run tests
```

## Running Live Tests

Live tests require a Monarch Money account:

```bash
export MONARCH_LIVE_TESTS=1
make test-live
```

⚠️ **Warning:** Use a test account, not your primary financial data.

## Pull Request Process

1. Fork and clone the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run `make verify` to ensure all checks pass
5. Commit with a descriptive message
6. Push and open a PR

## Code Style

- We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Type hints are required (strict mypy)
- Tests are required for new features

## Questions?

Open an issue for discussion before starting large changes.
```

---

### 8. Add SECURITY.md ⏱️ 5 min

**Dependency:** Requires `AUTHOR_EMAIL` decision from Prerequisites.

Create `SECURITY.md` in repo root:

```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue.

Instead, please email ${AUTHOR_EMAIL} with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact

We will respond within 48 hours and work with you to address the issue.

## Security Considerations

### Credential Storage

Monarch CLI stores session tokens (not passwords) using:

1. **System keyring** (preferred) - OS-level secure storage
2. **File storage** - `~/.config/monarch-cli/session.json` with 600 permissions

### What We Don't Store

- Passwords are never stored after authentication
- No financial data is cached locally
- Session tokens are the only persisted credential

### Environment Variables

The `MONARCH_TOKEN` environment variable can be used for automation.
**Caution:** Do not expose this in logs, scripts committed to repos, or CI outputs.
```

---

### 9. Add CODE_OF_CONDUCT.md ⏱️ 3 min

Create `CODE_OF_CONDUCT.md` in repo root (standard Contributor Covenant):

```markdown
# Contributor Covenant Code of Conduct

## Our Pledge

We as members, contributors, and leaders pledge to make participation in our
community a harassment-free experience for everyone, regardless of age, body
size, visible or invisible disability, ethnicity, sex characteristics, gender
identity and expression, level of experience, education, socio-economic status,
nationality, personal appearance, race, religion, or sexual identity
and orientation.

## Our Standards

Examples of behavior that contributes to a positive environment:

* Using welcoming and inclusive language
* Being respectful of differing viewpoints and experiences
* Gracefully accepting constructive criticism
* Focusing on what is best for the community
* Showing empathy towards other community members

Examples of unacceptable behavior:

* The use of sexualized language or imagery and unwelcome sexual attention
* Trolling, insulting/derogatory comments, and personal or political attacks
* Public or private harassment
* Publishing others' private information without explicit permission
* Other conduct which could reasonably be considered inappropriate

## Enforcement

Instances of abusive, harassing, or otherwise unacceptable behavior may be
reported to the project maintainers. All complaints will be reviewed and
investigated promptly and fairly.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant](https://www.contributor-covenant.org/),
version 2.1, available at
https://www.contributor-covenant.org/version/2/1/code_of_conduct.html
```

---

### 10. Add GitHub Issue Templates ⏱️ 10 min

Create directory structure:
```bash
mkdir -p .github/ISSUE_TEMPLATE
```

Create `.github/ISSUE_TEMPLATE/bug_report.md`:
```markdown
---
name: Bug Report
about: Report a bug to help us improve
title: '[BUG] '
labels: bug
assignees: ''
---

## Description

A clear description of what the bug is.

## Steps to Reproduce

1. Run `monarch ...`
2. See error

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened. Include full error output if applicable.

## Environment

- **OS:** [e.g., macOS 14.2, Ubuntu 22.04, Windows 11]
- **Python version:** [e.g., 3.12.1 - run `python --version`]
- **monarch-cli version:** [e.g., 0.1.0 - run `monarch --version`]
- **Installation method:** [pip, uv, pipx]

## Additional Context

Any other context, logs, or screenshots.
```

Create `.github/ISSUE_TEMPLATE/feature_request.md`:
```markdown
---
name: Feature Request
about: Suggest an idea for this project
title: '[FEATURE] '
labels: enhancement
assignees: ''
---

## Problem Statement

What problem does this solve? What's the use case?

## Proposed Solution

How would you like this to work? Include example commands if applicable.

```bash
# Example of how the feature might work
monarch new-command --flag value
```

## Alternatives Considered

Any other approaches you've thought about.

## Additional Context

Any other context, mockups, or examples from similar tools.
```

Create `.github/ISSUE_TEMPLATE/config.yml`:
```yaml
blank_issues_enabled: true
contact_links:
  - name: Documentation
    url: https://github.com/${GITHUB_OWNER}/monarch-cli#readme
    about: Check the README for usage instructions
```

---

### 11. Add PyPI Publish Workflow ⏱️ 15 min

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi  # Create this environment in GitHub repo settings
    permissions:
      id-token: write  # Required for trusted publishing

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run quality checks
        run: |
          uv run ruff format --check .
          uv run ruff check .
          uv run mypy src/
          uv run pytest -m "not live" --tb=short

      - name: Build package
        run: uv build

      - name: Validate package
        run: uv run twine check dist/*

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # No token needed - uses OpenID Connect trusted publishing
```

**Required Setup After Creating Workflow:**

1. Go to https://pypi.org/manage/account/publishing/
2. Add a new pending publisher:
   - PyPI Project Name: `monarch-cli`
   - Owner: `${GITHUB_OWNER}`
   - Repository name: `monarch-cli`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. In GitHub repo Settings → Environments → Create "pypi" environment

---

### 12. Add prepublish Target to Makefile ⏱️ 3 min

Add this target at the **end** of `Makefile`:

```makefile
# Pre-publish verification (run before `twine upload`)
prepublish: verify
	rm -rf dist/ build/ *.egg-info
	uv build
	@echo "✓ Build successful"
	uv run twine check dist/*
	@echo "✓ Package metadata valid"
	uv run python -m readme_renderer README.md > /dev/null
	@echo "✓ README renders correctly"
	@echo ""
	@echo "Package ready! Next steps:"
	@echo "  1. Test: twine upload --repository testpypi dist/*"
	@echo "  2. Publish: twine upload dist/*"
```

Also add `prepublish` to the `.PHONY` line at the top:
```makefile
.PHONY: setup verify format format-check lint lint-fix typecheck test prepublish
```

---

### 13. Verify Shell Completions Work ⏱️ 5 min

Typer provides shell completion support. Verify it works:

```bash
# Test completion script generation (don't actually install)
monarch --show-completion bash > /dev/null && echo "✓ bash completion works"
monarch --show-completion zsh > /dev/null && echo "✓ zsh completion works"
monarch --show-completion fish > /dev/null && echo "✓ fish completion works"
```

If any fail, check that Typer is correctly configured. The README already documents installation - just verify the feature works.

---

## 🛑 CHECKPOINT 2: Pre-Publish Review

**STOP HERE.** Final human review before publishing to PyPI.

### Review Checklist

1. **All P0 and P1 items complete:**
   ```bash
   # Verify no placeholder URLs remain
   grep -rn "yourusername\|OWNER\|your-email\|example\.com" \
       . --include="*.md" --include="*.toml" --include="*.yml" \
       | grep -v node_modules | grep -v .venv
   # Should return NO results (except this plan file)
   ```

2. **All checks pass:**
   ```bash
   make verify
   make prepublish
   ```

3. **Files exist:**
   ```bash
   ls -la LICENSE README.md CHANGELOG.md CONTRIBUTING.md \
       SECURITY.md CODE_OF_CONDUCT.md pyproject.toml
   ls -la .github/workflows/publish.yml
   ls -la .github/ISSUE_TEMPLATE/
   ```

4. **Git is clean:**
   ```bash
   git status  # Should show clean working tree or only expected changes
   git log --oneline -5  # Review recent commits
   ```

### ✅ Checkpoint Complete When

- [ ] All verification commands pass
- [ ] Human has reviewed package on TestPyPI
- [ ] Human is ready to publish (this is irreversible for this version number)

### Publish Commands (Human Only)

```bash
# Final build
rm -rf dist/
uv build
uv run twine check dist/*

# Publish to PyPI (IRREVERSIBLE)
uv run twine upload dist/*

# Tag release
git tag v0.1.0
git push origin main
git push origin v0.1.0

# Create GitHub Release at:
# https://github.com/${GITHUB_OWNER}/monarch-cli/releases/new
# - Select tag: v0.1.0
# - Title: v0.1.0
# - Copy release notes from CHANGELOG.md
# - Publish
```

---

## 🟡 P2: Post-Release Improvements

Track these for v0.2.0. Not blocking initial release.

### Documentation
- [ ] Add API rate limiting documentation
- [ ] Add troubleshooting section for common errors
- [ ] Consider a GitHub Pages docs site (sphinx/mkdocs)

### Package Improvements
- [ ] Consider single-source versioning with `hatch-vcs` (removes need to update version in 2 places)
- [ ] Add `--version --verbose` to show git commit SHA
- [ ] Add `monarch doctor` command (combine auth doctor + system checks)

### CI/CD
- [ ] Add coverage badge to README
- [ ] Add test matrix for Python 3.12 and 3.13
- [ ] Add dependabot.yml for dependency updates
- [ ] Add spell checking with `typos-cli`

### Code Quality
- [ ] Add more granular exception types
- [ ] Consider async progress bars for long operations
- [ ] Split large command files if they grow

### API Coverage
- [ ] `monarch goals list/show` - Financial goals
- [ ] `monarch rules list` - Auto-categorization rules
- [ ] `monarch net-worth` - Net worth tracking
- [ ] `monarch export` - Data export functionality

---

## Time Estimates

| Phase | Items | Est. Time | Human Required |
|-------|-------|-----------|----------------|
| **CHECKPOINT 0** | Prerequisites | ~10 min | ✅ Yes |
| **Phase 1 (P0)** | 6 items | ~35 min | ❌ No (agent) |
| **CHECKPOINT 1** | Verify TestPyPI | ~10 min | ✅ Yes |
| **Phase 2 (P1)** | 7 items | ~50 min | ❌ No (agent) |
| **CHECKPOINT 2** | Pre-publish review | ~10 min | ✅ Yes |
| **Publish** | Upload + tag | ~5 min | ✅ Yes |
| **Total** | | **~2 hours** | 4 human touchpoints |

---

## Quick Reference: File Status

| File | Purpose | Status |
|------|---------|--------|
| `LICENSE` | Legal terms | ✅ Done (verify author) |
| `README.md` | Project overview | ⚠️ Fix URL placeholder |
| `CHANGELOG.md` | Version history | ⚠️ Fix URL placeholders |
| `pyproject.toml` | Package metadata | ⚠️ Add classifiers, URLs, author |
| `CONTRIBUTING.md` | Contribution guide | ❌ Create (P1-7) |
| `SECURITY.md` | Security policy | ❌ Create (P1-8) |
| `CODE_OF_CONDUCT.md` | Community standards | ❌ Create (P1-9) |
| `.github/workflows/ci.yml` | CI pipeline | ✅ Done |
| `.github/workflows/publish.yml` | PyPI publish | ❌ Create (P1-11) |
| `.github/ISSUE_TEMPLATE/` | Issue templates | ❌ Create (P1-10) |
| `py.typed` | PEP 561 marker | ✅ Done |
| `Makefile` | Dev shortcuts | ⚠️ Add prepublish (P1-12) |

---

## References

- [Python Packaging User Guide](https://packaging.python.org/)
- [PyPI Classifiers](https://pypi.org/classifiers/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Contributor Covenant](https://www.contributor-covenant.org/)
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
- [uv Documentation](https://docs.astral.sh/uv/)
- [Twine Documentation](https://twine.readthedocs.io/)
