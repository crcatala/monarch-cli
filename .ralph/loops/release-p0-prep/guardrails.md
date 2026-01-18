# Guardrails: Release P0 Prep

## Values

Use these values throughout:
- **GITHUB_OWNER:** crcatala
- **AUTHOR_NAME:** Christian Catalan
- **AUTHOR_EMAIL:** crcatala@gmail.com

## Code Quality

- Run `make verify` before committing
- Do not introduce new linting errors
- Maintain existing test coverage

## File Modifications

- Only modify files specified in task acceptance criteria
- Do not change version numbers
- Do not modify source code (src/)

## No Publishing

- Do NOT upload to PyPI or TestPyPI
- Do NOT run `twine upload`
- Building and local testing only

## Commit Messages

Format: `release: <description> (mc-XXXX)`

Example: `release: fix placeholder URLs in README and CHANGELOG (mc-27a3)`
