---
id: mc-qqp7
status: closed
deps: []
links: []
created: 2026-09-20T00:00:00Z
type: bug
priority: 1
assignee: cc-vps
parent: mc-1568
tags: [phase-5, testing, isolation, ci, regression]
---
# Isolate the test suite from real credentials and shared client state

The non-live test suite is environment-dependent: it passes on headless CI but
fails on a developer workstation that has a stored Monarch token. On macOS it
also triggers an OS Keychain access prompt during a test run and issues real
API calls, producing three failures in `make test` / `make prepublish`.

## Reproduction

On a machine whose OS keyring holds a `com.monarch-cli` token (or whose home
directory contains a legacy `~/.mm/mm_session.pickle`):

```
make test
```

Observed failures:

- `tests/commands/test_auth.py::TestLegacyArtifactSafety::test_authenticated_command_failure_mentions_legacy_artifact`
- `tests/test_mutation_policy.py::TestReadOnlyDefault::test_read_only_commands_usable_without_authorization`
- `tests/core/test_prompting.py::TestCliNonInteractive::test_interactive_login_behavior_unchanged`

The first two report a live `401 Unauthorized` from
`https://api.monarch.com/graphql` instead of `AUTH_REQUIRED` / the legacy
re-auth guidance. The third reports two `typer.prompt` calls (`Email`, then
`Enter choice`) where the test asserts exactly one. A macOS Keychain prompt
appears during the run.

All three pass on CI, where no keyring backend holds a token.

## Root cause

Three independent isolation gaps, none of which are the credential code's
fault:

1. **No suite-wide keyring isolation.** Tests that assume "no credential is
   available" call the real `keyring.get_password` (through
   `session._get_from_keyring`). On CI this returns nothing; on a workstation
   it returns a real token, so the CLI builds an authenticated client and hits
   the network. Reading the item is what triggers the macOS Keychain prompt.

2. **The authenticated-client singleton leaks across tests.**
   `core/adapter.py` caches one `MonarchMoney` instance in a module-level
   `_client`. A test that creates a real client (via gap 1) poisons every later
   test: `get_authenticated_client()` returns the cached instance *before*
   consulting the token, so tests that mock `adapter.get_session_token` /
   `adapter.legacy_artifact_exists` are bypassed entirely and still issue live
   calls. `tests/core/test_adapter.py` and `tests/test_mutation_policy.py`
   reset the cache locally, but nothing resets it between the other test
   modules.

3. **No config-dir or legacy-artifact isolation.** `get_config_dir()` falls
   back to the user's real config directory, and `COMPAT_SESSION_PATH` points
   at the user's real `~/.mm/mm_session.pickle`, so a developer's local config
   and legacy file can change test outcomes.

A fourth, test-local issue: `test_interactive_login_behavior_unchanged`
asserts `typer.prompt` is called exactly once, but `auth login` additionally
prompts for the storage backend whenever `_is_keyring_available()` is true.
That is correct product behavior; the assertion is only deterministic on hosts
without a keyring backend.

## Why existing tests miss it

Every affected test is correct in isolation on CI. The gaps are cross-cutting:
there is no single fixture that provably prevents a test from touching the OS
keyring, the user's config directory, the legacy pickle path, or the cached
client. Local fixes in individual modules do not compose.

## Design

Add one documented, autouse `_isolate_credentials` fixture in
`tests/conftest.py` that makes every test hermetic:

- reset `core.adapter._client` before and after each test;
- stub the **library-level** `keyring.get_password` to return `None`, so no
  test can reach the OS keyring even through a code path that does not go
  through `session._get_from_keyring`;
- point `session.COMPAT_SESSION_PATH` at the test's `tmp_path`;
- clear `MONARCH_TOKEN`, `MONARCH_SESSION_PATH`, `MONARCH_CONFIG_DIR`, and
  `MONARCH_NON_INTERACTIVE`, and set `MONARCH_CONFIG_DIR` to `tmp_path`;
- reset the shared prompt-policy, mutation-authorization, and config globals.

Stub the library seam rather than the application helper: the OS keyring read
is the side-effecting boundary, so stubbing it stays correct regardless of how
the application code is refactored. Tests that deliberately exercise keyring
behavior replace `session.keyring` inside the test and continue to work
unchanged.

Make `test_interactive_login_behavior_unchanged` deterministic by pinning
`_is_keyring_available` to `False`, matching the single-prompt path the test
intends to pin.

Do **not** refactor the `adapter._client` singleton for testability: it is
correct production behavior (one authenticated client per process invocation)
and injecting it would spread test concerns into call sites. A fixture reset is
the conventional fix.

## Acceptance criteria

- [x] `make verify` passes on a workstation with a populated OS keyring.
- [x] The non-live suite never reads the real OS keyring, the user's config
      directory, or the user's legacy pickle path.
- [x] The cached authenticated client cannot leak between tests.
- [x] `test_interactive_login_behavior_unchanged` is deterministic regardless
      of local keyring availability.
- [x] No production code changes.

## Notes
