.PHONY: verify format format-check lint lint-fix typecheck test

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

# Run tests with pytest
test:
	uv run pytest
