# Releasing

This is the single source of truth for releasing monarch-cli. Follow the steps
in order. Every command below is safe to run from the repository root.

The release has two independent destinations:

- **GitHub Releases** — tag + changelog + wheel/sdist assets (created by `make release`).
- **PyPI** — the published package (uploaded manually; `make release` never publishes to PyPI).

TestPyPI is a dry run for the PyPI upload. **Always test on TestPyPI first.**

## TL;DR (happy path)

```bash
# 1. Bump the version in three places + CHANGELOG (see Step 1)
# 2. Verify, build, and validate — wipes and rebuilds dist/
make prepublish

# 3. Upload to TestPyPI and verify a clean install
uv run twine upload --repository testpypi dist/*

# 4. Create the git tag + GitHub release (does NOT touch PyPI)
make release-dry   # preview
make release       # for real

# 5. Publish to PyPI
uv run twine upload dist/*
```

If any step fails, jump to [Failure recovery](#failure-recovery). Every guard
prints an exact cause and the next action.

## Prerequisites

### 1. Create PyPI accounts

You need accounts on both TestPyPI (for testing) and PyPI (for production):

- **TestPyPI:** https://test.pypi.org/account/register/
- **PyPI:** https://pypi.org/account/register/

### 2. Create API tokens

- **TestPyPI:** https://test.pypi.org/manage/account/token/
- **PyPI:** https://pypi.org/manage/account/token/

Select "Entire account" scope for first-time uploads. After publishing, you can
create project-scoped tokens for tighter security.

### 3. Configure `~/.pypirc`

```ini
[testpypi]
  username = __token__
  password = pypi-YOUR_TEST_PYPI_TOKEN

[pypi]
  username = __token__
  password = pypi-YOUR_PYPI_TOKEN
```

Secure the file and sanity-check it:

```bash
chmod 600 ~/.pypirc
uv run twine upload --repository testpypi --help >/dev/null && echo "twine available"
```

> Tokens are secrets. Never paste `~/.pypirc` contents into a shell, issue
> tracker, or chat. Rotate a token immediately if it is exposed.

## Release workflow

### Step 1: Update version and changelog

The version lives in three files and they **must all agree**. `make prepublish`
and `scripts/release.sh` both verify this and fail with a clear message if they
drift.

| File | Field | Why it matters |
|------|-------|----------------|
| `src/monarch_cli/__init__.py` | `__version__` | Source of the git tag (`v<version>`) and `monarch --version` |
| `pyproject.toml` | `[project].version` | Version embedded in the built wheel/sdist |
| `uv.lock` | `monarch-cli` package version | Keeps the locked editable install consistent |

Update all three, then refresh the lock:

```bash
# 1. edit src/monarch_cli/__init__.py        -> __version__ = "X.Y.Z"
# 2. edit pyproject.toml                     -> version = "X.Y.Z"
uv lock                                      # syncs uv.lock
```

Update `CHANGELOG.md`:

1. Move the `## [Unreleased]` content under a new header
   `## [X.Y.Z] - YYYY-MM-DD`.
2. Add a fresh empty `## [Unreleased]` section at the top.
3. Update the comparison links at the bottom:

   ```markdown
   [Unreleased]: https://github.com/crcatala/monarch-cli/compare/vX.Y.Z...HEAD
   [X.Y.Z]: https://github.com/crcatala/monarch-cli/compare/vPREV...vX.Y.Z
   ```

No capabilities-fixture regeneration is needed for a version bump: the
canonical capabilities fixture (`tests/fixtures/capabilities.manifest.json`)
stores a fixed placeholder CLI version and is decoupled from `__version__`. Only
after an *intentional* capabilities manifest change (a new command, option,
effect, or schema reference) run `make update-capabilities-fixture` and review
the diff. See `docs/capabilities.md`.

Commit everything before continuing — the release script refuses to run with a
dirty working tree.

### Step 2: Verify, build, and validate

```bash
make prepublish
```

This is the one command that proves the release is publishable. It runs, in order:

1. `format-check`, `lint`, `typecheck`, `test` (`verify`) — includes the
   version-parity and capabilities-fixture contract tests.
2. `smoke-install` — **wipes `dist/`**, rebuilds the wheel and sdist with
   `uv build`, installs the wheel into a throwaway environment outside the
   source tree, and runs both `monarch` and `monarch-cli` entry points.
3. `twine check dist/*` — validates distribution metadata.
4. `readme_renderer` — confirms the README renders on PyPI.

Success ends with all tests passing, followed by `smoke-install OK`,
`✓ Package metadata valid`, and `✓ README renders correctly`.

> **`dist/` is not a cache.** `make prepublish`, `make smoke-install`, and
> `make release` each wipe and rebuild `dist/`, so the artifacts always match
> the current metadata. Do **not** run a bare `uv build` and then upload — it
> *adds* files without removing old ones, leaving a mixed-version `dist/` that
> PyPI rejects. Let the smoke-install target manage `dist/`.

### Step 3: Test on TestPyPI

Upload the freshly built artifacts:

```bash
uv run twine upload --repository testpypi dist/*
```

Then verify a clean install in a throwaway virtualenv (the
`--extra-index-url` is required because TestPyPI does not host the runtime
dependencies):

```bash
python -m venv /tmp/test-monarch
source /tmp/test-monarch/bin/activate
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ monarch-cli==X.Y.Z
monarch --version    # should print: monarch-cli X.Y.Z
monarch --help
deactivate
rm -rf /tmp/test-monarch
```

Confirm the page renders correctly: `https://test.pypi.org/project/monarch-cli/`.

TestPyPI versions are immutable, just like PyPI. If you need to fix and re-test,
bump to a new version (for example `X.Y.Zrc2`) — you cannot overwrite.

### Step 4: Create the GitHub release

Once TestPyPI looks good:

```bash
make release-dry   # preview every action and the changelog that will be used
make release       # create tag + GitHub release (does NOT publish to PyPI)
```

`make release` verifies, in order:

- `__init__.py` and `pyproject.toml` versions match;
- the tag `vX.Y.Z` does not already exist;
- the working tree is clean;
- a `## [X.Y.Z]` changelog section exists;
- it is on `main` (warns and prompts otherwise);
- after building, `dist/monarch_cli-X.Y.Z-*.whl` exists.

It then builds via `make smoke-install`, prompts for confirmation, creates and
pushes the annotated tag `vX.Y.Z`, and creates the GitHub release with the
changelog as notes and `dist/*` as assets.

### Step 5: Publish to PyPI

```bash
uv run twine upload dist/*
```

Verify at `https://pypi.org/project/monarch-cli/`.

## Command reference

| Action | Command |
|--------|---------|
| Bump lockfile after version edit | `uv lock` |
| Verify + build + validate (wipes `dist/`) | `make prepublish` |
| Rebuild + isolated install only | `make smoke-install` |
| Regenerate capabilities fixture (intentional manifest change only) | `make update-capabilities-fixture` |
| Upload to TestPyPI | `uv run twine upload --repository testpypi dist/*` |
| Verbose upload (shows the real server error) | `uv run twine upload --verbose --repository testpypi dist/*` |
| Preview GitHub release | `make release-dry` |
| Create GitHub release | `make release` |
| Upload to PyPI | `uv run twine upload dist/*` |

## Failure recovery

Each guard is designed to stop you *before* an irreversible action and tell you
exactly what to do. Find your symptom below.

### `400 Bad Request` / `HTTPError` from `twine upload`

Twine hides the server's reason by default. Re-run with `--verbose` (after
`upload`) to see it:

```bash
uv run twine upload --verbose --repository testpypi dist/*
```

The overwhelmingly common reason is:

```
400 File already exists ('monarch_cli-X.Y.Z-...whl', ...)
```

**Cause:** you are uploading a version that already exists (published versions
are immutable), usually because `dist/` is stale or was built before the version
bump.

**Fix:** rebuild so `dist/` matches the intended version, then re-upload:

```bash
make smoke-install   # wipes and rebuilds dist/
ls dist/             # confirm only monarch_cli-X.Y.Z-* files are present
uv run twine upload --repository testpypi dist/*
```

If the version genuinely already exists on the index and you need changes, bump
the version (Step 1) and start again. Never delete/re-upload a published version.

### `❌ Version mismatch` (from `make release`)

`src/monarch_cli/__init__.py` and `pyproject.toml` disagree. Set both to the
same version and run `uv lock`, then retry. The same invariant is enforced by
`make prepublish` via `tests/test_version_parity.py`.

### `❌ Tag vX.Y.Z already exists`

The tag was already created (a previous release, or you re-ran `make release`).
Either delete the tag if it was a mistake (`git tag -d vX.Y.Z && git push origin
:refs/tags/vX.Y.Z`) or bump the version and release that instead.

### `❌ Uncommitted changes detected`

Commit or stash your changes first. The release must correspond to a commit.
`git status --short` is printed for you.

### `❌ No changelog entry found for version X.Y.Z`

Add a `## [X.Y.Z]` section to `CHANGELOG.md` (Step 1), commit it, and retry.

### `capabilities manifest drifted from the canonical fixture`

Only legitimate after an *intentional* capabilities manifest change. Regenerate
and review the diff:

```bash
make update-capabilities-fixture
git diff tests/fixtures/capabilities.manifest.json
```

This is **not** needed for a version bump — the fixture is version-independent.

### Token not working

- Ensure there is no extra whitespace in `~/.pypirc`.
- The token must start with `pypi-`.
- Confirm the token is not expired or revoked, and that the username is exactly
  `__token__`.

### Package not installable from TestPyPI

TestPyPI does not host all dependencies. Always pass the production index as a
fallback:

```bash
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ monarch-cli==X.Y.Z
```

### "File already exists" on PyPI but you have not published this version

This means the version is already on the index (possibly from a teammate's
upload or an earlier attempt). Confirm with:

```bash
curl -s https://pypi.org/pypi/monarch-cli/json | python3 -c "import sys,json;print(list(json.load(sys.stdin)['releases']))"
```

If the version is present, you cannot re-upload it — bump the version.
