# Releasing

This guide covers the full release process for monarch-cli.

## Prerequisites

### 1. Create PyPI Accounts

You'll need accounts on both TestPyPI (for testing) and PyPI (for production):

- **TestPyPI:** https://test.pypi.org/account/register/
- **PyPI:** https://pypi.org/account/register/

### 2. Create API Tokens

Create API tokens for each account:

- **TestPyPI:** https://test.pypi.org/manage/account/token/
- **PyPI:** https://pypi.org/manage/account/token/

Select "Entire account" scope for first-time uploads. After publishing, you can create project-scoped tokens for better security.

### 3. Configure ~/.pypirc

Create `~/.pypirc` with your tokens:

```ini
[testpypi]
  username = __token__
  password = pypi-YOUR_TEST_PYPI_TOKEN

[pypi]
  username = __token__
  password = pypi-YOUR_PYPI_TOKEN
```

Secure the file:

```bash
chmod 600 ~/.pypirc
```

## Release Workflow

### Step 1: Update Version & Changelog

1. Update version in `src/monarch_cli/__init__.py`
2. Update `CHANGELOG.md` with release notes under the new version header

### Step 2: Verify & Build

Run the prepublish target to verify everything and build the package:

```bash
make prepublish
```

This runs all quality checks (format, lint, typecheck, test), builds the package, validates metadata with twine, and confirms the README renders correctly.

### Step 3: Test on TestPyPI

Upload to TestPyPI first:

```bash
uv run twine upload --repository testpypi dist/*
```

Verify the upload:

```bash
# Install in a fresh environment
python -m venv /tmp/test-monarch
source /tmp/test-monarch/bin/activate
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ monarch-cli

# Test it works
monarch --version
monarch --help

# Cleanup
deactivate
rm -rf /tmp/test-monarch
```

Check the package page looks correct: `https://test.pypi.org/project/monarch-cli/`

### Step 4: Create GitHub Release

Once TestPyPI looks good, create the GitHub release:

```bash
make release-dry  # Preview what will happen
make release      # Create tag + GitHub release
```

This will:
- Create a git tag (e.g., `v0.1.0`)
- Push the tag to GitHub
- Create a GitHub release with changelog notes
- Upload wheel and tarball as release assets

### Step 5: Publish to PyPI

After the GitHub release is created:

```bash
uv run twine upload dist/*
```

Verify at: `https://pypi.org/project/monarch-cli/`

## Quick Reference

| Action | Command |
|--------|---------|
| Verify + build + validate | `make prepublish` |
| Upload to TestPyPI | `uv run twine upload --repository testpypi dist/*` |
| Upload to PyPI | `uv run twine upload dist/*` |
| Preview GitHub release | `make release-dry` |
| Create GitHub release | `make release` |

## Troubleshooting

### "File already exists" error

PyPI doesn't allow re-uploading the same version. You must bump the version number for any new upload.

### Token not working

- Ensure no extra whitespace in `~/.pypirc`
- Token should start with `pypi-`
- Check token hasn't expired or been revoked

### Package not installable from TestPyPI

TestPyPI may not have all dependencies. Use `--extra-index-url` to fall back to PyPI:

```bash
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ monarch-cli
```
