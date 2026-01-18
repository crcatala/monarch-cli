# Guardrails: Release P1 Community Files

## Values

Use these values throughout:
- **GITHUB_OWNER:** crcatala
- **AUTHOR_NAME:** Christian Catalan
- **AUTHOR_EMAIL:** crcatala@gmail.com

## Code Quality

- Run `make verify` before committing
- Do not introduce new linting errors
- New files should follow existing project style

## File Creation Rules

- Create files in correct locations (repo root or .github/)
- Use templates from plans/RELEASE-READINESS-v0.1.0.md
- Verify no placeholder variables remain (${...}, OWNER, yourusername)

## No Publishing

- Do NOT upload to PyPI or TestPyPI
- Do NOT run `twine upload`
- Creating the publish workflow file is fine, but do not trigger it

## Commit Messages

Format: `docs: <description> (mc-XXXX)` or `ci: <description> (mc-XXXX)`

Examples:
- `docs: add CONTRIBUTING.md (mc-3aa3)`
- `ci: add PyPI publish workflow (mc-b9f6)`
