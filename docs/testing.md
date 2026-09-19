# Testing

The normal verification target is:

```bash
make verify
```

It runs formatting checks, Ruff, mypy, and the non-live pytest suite.

## Read-only live tests

The read-only live suite requires an authenticated Monarch account and internet
access. Use a dedicated test account and never commit credentials or responses.

```bash
MONARCH_LIVE_TESTS=1 make test-live
```

The target runs only tests marked `live` and excludes mutation tests. Calls are
spaced by at least one second by default; increase the delay with
`MONARCH_LIVE_DELAY` if needed. Do not repeatedly retry failures caused by
service errors or rate limits.

## Gated live mutation tests

The mutation suite is separately gated and uses only disposable fixtures that
it creates itself. It requires an owner-approved household ID and must never be
run against an existing financial record.

```bash
# Authenticate with the exact CLI used by the test suite
uv run monarch auth login

# Export the approved disposable household ID; do not persist or commit it
export MONARCH_LIVE_MUTATION_HOUSEHOLD_ID=<approved-household-id>

# Run the gated suite
MONARCH_LIVE_MUTATION_TESTS=1 make test-live-mutation
```

The suite creates uniquely marked manual fixtures, verifies the approved
household before the first mutation, and cleans up the fixtures afterward. It
fails closed when the environment or household does not match its safety
checks.

Each run journals intended and observed fixture effects in the ignored
`.monarch-live-mutation-recovery/` directory. If a create or delete becomes
ambiguous, do not retry blindly; inspect the disposable household and follow
the recovery instructions in the manifest.

The ordinary `make test` and CI suite exclude all live tests.
