# Configuration and authentication

Monarch CLI reads configuration from built-in defaults, a TOML config file,
environment variables, and command-line flags.

For most settings, precedence is:

```text
defaults → config file → environment → CLI flags
```

`--allow-mutations` is deliberately separate: it is invocation-only and cannot
be set through configuration or an environment variable.

## Configuration file

The default file is `config.toml` inside the platform-specific Monarch CLI
configuration directory. On Linux this is normally:

```text
~/.config/monarch-cli/config.toml
```

Set `MONARCH_CONFIG_DIR` to use another directory. Supported keys are:

```toml
# plain, json, table, csv, or compact
format = "plain"
color = true
verbose = false
debug = false
quiet = false
timeout = 30
max_retries = 3
confirm_destructive = true
non_interactive = false
```

`timeout` is the timeout for each API attempt. `max_retries` applies to
transient failures from read commands only; remote mutations never retry
automatically.

`confirm_destructive = false` is equivalent to using `--yes` for commands that
ask for destructive confirmation. It still does not authorize a remote write;
`--allow-mutations` remains required.

## Environment variables

| Variable | Purpose |
|---|---|
| `MONARCH_TOKEN` | Use an existing authentication token |
| `MONARCH_CONFIG_DIR` | Override the configuration directory |
| `MONARCH_SESSION_PATH` | Override the JSON session-file path |
| `MONARCH_FORMAT` | Default output format |
| `MONARCH_VERBOSE` | Enable progress output (`1`, `true`, or `yes`) |
| `MONARCH_DEBUG` | Enable stack traces |
| `MONARCH_QUIET` | Emit IDs only |
| `MONARCH_TIMEOUT` | Per-attempt timeout in seconds |
| `MONARCH_MAX_RETRIES` | Read retry count |
| `MONARCH_NO_COLOR` | Disable color when truthy |
| `NO_COLOR` | Disable color when set, following no-color.org |
| `MONARCH_NON_INTERACTIVE` | Fail instead of prompting when truthy |

## Authentication priority

When making an authenticated request, the CLI checks credentials in this
order:

1. `MONARCH_TOKEN`
2. system keyring
3. JSON session file

Interactive login stores only the session token, never the password. Keyring is
preferred for personal machines; file storage is useful on headless systems
without a usable keyring:

```bash
monarch auth login --storage keyring
monarch auth login --storage file
```

Use `monarch auth setup` to see the active storage path and security guidance.
Legacy `~/.mm/mm_session.pickle` files are never deserialized or used as
credentials.

## Non-interactive automation

Use `--non-interactive` when a process must never wait for input:

```bash
monarch --non-interactive auth login
```

A blocked prompt exits with code `5` and emits a structured `PROMPT_BLOCKED`
error on stderr. Non-interactive mode does not authorize mutations, answer
destructive confirmations, or replace explicit input channels such as
`transactions batch-update --stdin`.

For an automated write, use explicit authorization and, when needed, explicit
confirmation bypass separately:

```bash
monarch --non-interactive --allow-mutations --yes \
  transactions tags clear --transaction-id TXN_ID
```

## Retry and mutation safety

Read commands retry configured transient network failures with exponential
backoff. Remote mutations make exactly one attempt because a timeout or
connection loss may occur after the server has applied the change.

If a remote result is uncertain, the CLI emits an ambiguous mutation outcome
and exits `4`. Verify remote state before retrying. See
[Mutation outcomes](mutation-outcomes.md) for the result envelope and recovery
rules.
