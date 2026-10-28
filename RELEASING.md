# Releasing

Releases are cut by hand from a clean `main`. `make release` creates the tag
and the GitHub Release; the PyPI upload is a separate, last step from the
tagged commit, so a failed upload never leaves a half-made tag.

TestPyPI is a rehearsal for the PyPI upload. Publishing versions are immutable
on both indexes.

`scripts/prep-release.sh`, `scripts/check-changelog.sh`, and
`scripts/build_info.py` are canonical release-standard files; do not edit them
in place. Project specifics live in `scripts/release.sh`,
`scripts/smoke_install.sh`, `scripts/bump.sh`, and this file.

## Prerequisites

- Push access to `main`; `gh auth status` succeeds.
- PyPI and TestPyPI API tokens. `twine` reads `~/.pypirc`:

  ```ini
  [testpypi]
    username = __token__
    password = pypi-YOUR_TEST_PYPI_TOKEN

  [pypi]
    username = __token__
    password = pypi-YOUR_PYPI_TOKEN
  ```

  `chmod 600 ~/.pypirc`. Tokens are secrets: never paste the file into a
  shell, issue tracker, or chat; rotate a token immediately if it is exposed.

## Before releasing

1. `git checkout main && git pull --ff-only`
2. `bash scripts/prep-release.sh`. Paste the output into an LLM, review the
   result, and put the user-facing entries under `## [Unreleased]` in
   `CHANGELOG.md` (Keep a Changelog groups: Added, Changed, Fixed, Removed,
   Security). Commit the changelog to `main`.

## Release

```bash
make bump VERSION=X.Y.Z   # version metadata + changelog section,
                          # commit "chore: release vX.Y.Z"
git push                  # the release commit must be on origin/main before tagging
make prepublish           # verify, stamp, build, isolated install, --version check
make release-dry          # preview the tag and GitHub Release
make release              # tag vX.Y.Z (annotated "Release X.Y.Z"), push,
                          # GitHub Release with the changelog and dist/ attached
uv run twine upload --repository testpypi dist/*   # optional rehearsal
uv run twine upload dist/*                         # last: publish the tagged build
```

### `make bump VERSION=X.Y.Z`

Writes the version in every place it is declared and commits the release:

| File | Field | Why it matters |
|------|-------|----------------|
| `src/monarch_cli/__init__.py` | `__version__` | Source of the git tag (`v<version>`) |
| `pyproject.toml` | `[project].version` | Version embedded in the built wheel/sdist |
| `uv.lock` | `monarch-cli` package version | Keeps the locked install consistent (`uv lock`) |
| `CHANGELOG.md` | Unreleased → `## [X.Y.Z] - YYYY-MM-DD` | GitHub Release notes |

It refuses a dirty tree, a branch other than `main`, an existing tag, or an
empty Unreleased section (`bash scripts/check-changelog.sh`). `make prepublish`
and `scripts/release.sh` re-check that the source and `pyproject.toml`
versions agree.

No capabilities-fixture regeneration is needed for a version bump: the
canonical capabilities fixture (`tests/fixtures/capabilities.manifest.json`)
stores a fixed placeholder CLI version and is decoupled from `__version__`.
Only after an *intentional* capabilities manifest change (a new command,
option, effect, or schema reference) run `make update-capabilities-fixture` and
review the diff. See `docs/capabilities.md`.

### `make prepublish`

The one command that proves the release is publishable. It runs, in order:

1. `format-check`, `lint`, `typecheck`, `test` (`verify`) — includes the
   version-parity and capabilities-fixture contract tests.
2. `smoke-install` — stamps `src/monarch_cli/_build_info.json` from `HEAD`,
   **wipes `dist/`**, rebuilds the wheel and sdist with `uv build`, checks that
   both artifacts ship the stamp, installs the wheel into a throwaway
   environment outside the source tree, and checks that `monarch` and
   `monarch-cli` print exactly
   `monarch X.Y.Z (sha7 YYYY-MM-DD)` (with `-dirty` only when the stamp's tree
   was dirty).
3. `twine check dist/*` — validates distribution metadata.
4. `readme_renderer` — confirms the README renders on PyPI.

> **`dist/` is not a cache.** `make prepublish`, `make smoke-install`, and
> `make release` each wipe and rebuild `dist/`, so the artifacts always match
> the current commit. Do **not** run a bare `uv build` and then upload — it
> *adds* files without removing old ones, leaving a mixed-version `dist/` that
> PyPI rejects.

### `make release-dry` and `make release`

`make release-dry` previews every action and the changelog that will be used.
It warns (rather than refuses) when the branch is not `main`, `HEAD` is not
`origin/main`, or the version's tag already exists, so it can be run on an
unreleased branch. It never creates a tag or a release.

`make release` verifies, in order:

- `__init__.py` and `pyproject.toml` versions match;
- the working tree is clean and the branch is `main`;
- `HEAD` equals `origin/main` (the release commit was pushed);
- the tag `vX.Y.Z` does not already exist;
- a `## [X.Y.Z]` changelog section exists;
- `smoke-install` rebuilt `dist/` and the stamp in
  `src/monarch_cli/_build_info.json` is `HEAD`;
- `dist/monarch_cli-X.Y.Z-*.whl` exists.

It then prompts for confirmation, creates and pushes the annotated tag
`vX.Y.Z` (`Release X.Y.Z`), and creates the GitHub Release with the changelog
as notes and `dist/*` as assets. It never publishes to PyPI.

### Publish last

Upload from the same `dist/` built from the tagged commit:

```bash
uv run twine upload dist/*
```

Optionally rehearse on TestPyPI first:

```bash
uv run twine upload --repository testpypi dist/*
python -m venv /tmp/test-monarch
source /tmp/test-monarch/bin/activate
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ monarch-cli==X.Y.Z
monarch --version    # monarch X.Y.Z (sha7 YYYY-MM-DD)
deactivate && rm -rf /tmp/test-monarch
```

TestPyPI does not host the runtime dependencies, so the production index
fallback is required. TestPyPI versions are immutable too: to re-test, bump to
a new version (for example `X.Y.Zrc2`).

## When a step fails

- **Before `git push`**: nothing is on the remote yet. Fix and repeat;
  `git reset --hard origin/main` drops a local bump commit.
- **After `git push`, before `make release`**: the bump commit is on `main` but
  untagged. Fix the cause and continue from `make prepublish`; do not bump
  again.
- **`tag vX.Y.Z already exists`**: either delete the mistaken tag
  (`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`) or bump to the
  next version.
- **`HEAD is not origin/main`**: push the release commit first.
- **`No changelog entry found for version X.Y.Z`**: add the section (or use
  `make bump`) and commit it.
- **`dist/ was built from ... not HEAD`**: rebuild with `make prepublish`
  before tagging.
- **GitHub Release**: the tag is pushed. Create it with
  `gh release create vX.Y.Z dist/* --title vX.Y.Z --notes-file <section>`.
- **Upload `400 Bad Request` / `HTTPError`**: twine hides the reason. Re-run
  with `--verbose`; the usual cause is `File already exists`, meaning the
  version is already published. Never delete or re-upload a published version;
  bump instead. Files already on PyPI can be skipped with
  `uv publish --check-url https://pypi.org/simple/` (or just re-run twine).
- **Token not working**: no extra whitespace in `~/.pypirc`, the token starts
  with `pypi-`, the username is exactly `__token__`, and the token is not
  expired or revoked.

## Verify

```bash
monarch --version          # monarch X.Y.Z (sha7 YYYY-MM-DD)
monarch update --check     # 0 up to date, 1 update available, 2 unknown
uvx monarch-cli@latest --version
```
