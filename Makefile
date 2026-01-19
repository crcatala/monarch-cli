.PHONY: setup verify format format-check lint lint-fix typecheck test release release-dry prepublish

# Setup development environment (run once after cloning)
setup:
	uv sync --all-extras
	@# Clear any existing local core.hooksPath and hide global, so prek can install
	git config --local --unset-all core.hooksPath 2>/dev/null || true
	GIT_CONFIG_GLOBAL=/dev/null uv run prek install
	@# Override any global core.hooksPath with local setting
	git config --local core.hooksPath .git/hooks

# Run all verification steps
verify: format-check lint typecheck test

# Format code with ruff
format:
	uv run ruff format .

# Check code formatting (no changes)
format-check:
	uv run ruff format --check .

# Lint code (no auto-fix, for CI/verify)
lint:
	uv run ruff check .

# Lint and auto-fix issues
lint-fix:
	uv run ruff check . --fix

# Type checking with mypy
typecheck:
	uv run mypy src/

# Run tests with pytest (excludes live tests)
test:
	uv run pytest -m "not live"

# Run live tests only (requires MONARCH_LIVE_TESTS=1 and valid credentials)
test-live:
	MONARCH_LIVE_TESTS=1 uv run pytest tests/live/ -m live -v

# Create GitHub release with tag and changelog
release:
	./scripts/release.sh

# Dry-run release to see what would happen
release-dry:
	./scripts/release.sh --dry-run

# Pre-publish verification
prepublish: verify
	rm -rf dist/
	uv build
	@echo "✓ Build successful"
	uv run twine check dist/*
	@echo "✓ Package metadata valid"
	uv run python -m readme_renderer README.md > /dev/null
	@echo "✓ README renders correctly"
