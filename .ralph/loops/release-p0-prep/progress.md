# Progress Log: Release P0 Prep

## Codebase Patterns

*Document reusable patterns discovered during iterations here.*

---

## [2026-01-18 15:09] - fix-urls (mc-27a3)
- Replaced 'yourusername' placeholder with 'crcatala' in README.md and CHANGELOG.md
- Files changed: README.md, CHANGELOG.md
- **Learnings:** The grep for 'yourusername' will still find matches in `.tickets/`, `plans/`, and `.ralph/` directories - these are documentation references and should be excluded from verification using grep -v filters
---

## [2026-01-18 15:10] - update-author (mc-a5b0)
- Updated pyproject.toml authors field from "cc-vps" to "Christian Catalan" with correct email
- Updated LICENSE copyright line from "cc-vps" to "Christian Catalan"
- Files changed: pyproject.toml, LICENSE
- **Learnings:** None - straightforward text replacement
---

## [2026-01-18 15:11] - add-pypi-metadata (mc-2042)
- Added 12 PyPI classifiers (Development Status, Environment, License, Python versions, Topics, Typing)
- Added keywords array with finance-related terms
- Added [project.urls] section with Homepage, Documentation, Repository, Issues, Changelog
- Files changed: pyproject.toml
- **Learnings:** classifiers/keywords go in [project] section after requires-python; [project.urls] is a separate section
---

## [2026-01-18 15:12] - add-twine (mc-a77b)
- Added twine>=5.0.0 to dev dependencies in pyproject.toml
- Ran `uv sync --all-extras` to update uv.lock (installed twine 6.2.0 and dependencies)
- Verified `uv run twine --version` works correctly
- Files changed: pyproject.toml, uv.lock
- **Learnings:** None - straightforward dependency addition
---

## [2026-01-18 15:13] - verify-build (mc-c802)
- Verified complete build-to-install cycle for PyPI package
- Clean build with `uv build` creates wheel and sdist successfully
- Wheel contains all 39 expected files (monarch_cli modules, py.typed, dist-info)
- METADATA contains license (MIT), classifiers, keywords, project URLs
- `pip install dist/*.whl --force-reinstall` installs cleanly
- `monarch --version` shows 0.1.0, `--help` shows all 6 commands
- `monarch auth --help` shows all 6 auth subcommands
- Files changed: None (verification only task)
- **Learnings:** Build artifacts in dist/ are not tracked by git; pip install --force-reinstall is needed to replace an existing installation
---
