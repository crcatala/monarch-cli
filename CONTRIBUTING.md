# Contributing to Monarch CLI

Thank you for considering contributing!

## Development Setup

```bash
git clone https://github.com/crcatala/monarch-cli.git
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
