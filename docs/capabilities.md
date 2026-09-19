# Capabilities manifest

`monarch capabilities` prints one versioned JSON document describing the
installed CLI: every command path, argument, option, required input, default,
output support, safety requirement, interactivity, and published contract
version. Automation can use it to adapt to the installed version instead of
scraping styled help text or guessing whether an operation exists or changes
state.

```bash
monarch capabilities
monarch capabilities | jq '.commands[].path'
monarch capabilities | jq '.commands[] | select(.safety.requires_authorization)'
monarch capabilities | jq '.schema_contracts[].urn'
```

The command is side-effect free. Generating the manifest performs no
authentication lookup, client construction, network request, prompt, or
config/session creation or write.

## Manifest envelope

| Key | Meaning |
|---|---|
| `manifest_version` | Version of the manifest shape (`capabilities.v1`) |
| `taxonomy_version` | Version of the classification vocabulary |
| `cli` | CLI name, executable command, and installed version |
| `taxonomy` | Effect vocabulary and safety-flag names |
| `output` | Global formats, quiet behavior, mutation-outcome and raw policy |
| `safety` | Authorization, destructive-confirmation, and non-interactive policy |
| `schema_contracts` | Published schema contracts (name, version, stable URN) |
| `operation_contracts` | Mutation operation to outcome-schema/effect-entity mapping |
| `global` | Introspected global options |
| `commands` | One entry per registered command |

The document is serialized with sorted keys and fixed indentation, so repeated
runs over the same installation are byte-for-byte identical. A canonical
fixture test pins the shape, ordering, and serialization and fails if a
Typer/framework change silently alters the inventory.

## Command entries

Each entry under `commands` contains:

- `path` / `name` — the command path, for example `["transactions", "tags", "add"]`.
- `effects` — the explicit shared effect vocabulary for the command. Current
  values are `read_only`, `preview`, `remote_authentication`,
  `remote_mutation`, and `local_credential_change`. New effect members extend
  the taxonomy additively.
- `safety` — the explicit safety profile (never inferred):
  - `requires_authorization` — the command is a remote mutation and requires
    the global `--allow-mutations` option for this invocation.
  - `requires_destructive_confirmation` — the command requests destructive
    confirmation unless `--yes` is given. `--yes` never authorizes a write.
  - `interactive` — the command requests input from the user and cannot run
    under `--non-interactive`.
  - `supports_preview` — the command supports `--dry-run`, a validated
    no-effect preview that requires neither authorization nor confirmation.
- `output` — per-command output support:
  - `quiet` — records flow through the global ID-only `--quiet` behavior.
  - `ndjson` — the command supports `--ndjson` (per command, never global).
  - `raw` — the command supports `--raw` upstream passthrough.
  - `stable_normalized` — the command emits stable normalized output.
  - `schemas` — stable schema URNs the command emits.
- `arguments` and `options` — the introspected syntax, projected into plain
  dictionaries (`name`, `kind`, `flags`, `required`, `repeatable`, `type`,
  `choices`, `default`). Framework-internal object shapes are never exposed.

## Safety separation

The manifest keeps three independent safety concepts separate, matching the
CLI's runtime policy:

1. **Mutation authorization** — `--allow-mutations` in the global-option
   position authorizes remote mutations for one invocation only. It has no
   environment-variable or config-file equivalent.
2. **Destructive confirmation** — `--yes` (or `confirm_destructive = false`)
   skips the confirmation prompt. It never authorizes a remote write.
3. **Non-interactive mode** — `--non-interactive` (or
   `MONARCH_NON_INTERACTIVE=1`) fails instead of prompting. It never
   auto-answers a confirmation or authorizes a mutation.

A preview (`--dry-run`) is distinct from a mutation outcome: previews perform
no state change and are represented by `supports_preview`.

## Output stability

Global rendering formats (`plain`, `json`, `table`, `csv`, `compact`) and the
global `--quiet` behavior are described once under `output`. Per-command
`--ndjson` and `--raw` support are described per command, because they are not
global.

- Mutation outcomes always emit JSON and are never `--quiet`-compatible. Their
  contract is `urn:monarch-cli:schema:mutation-outcome:v1`.
- Stable normalized records are covered by the published schemas listed under
  `schema_contracts`; see [Machine-readable output schemas](schema-contracts.md).
- Raw passthrough (`--raw`) preserves upstream shapes and is **explicitly
  unschematized and unstable**; it has no schema URN.

Stable schema identifiers and contract versions come from the same
`monarch_cli.schemas` mapping published by `mc-cpzi`; the manifest cannot drift
from it without failing a completeness test.

## Versioning

`manifest_version` changes only for a breaking manifest-shape change.
Additive optional keys do not require a version change. Because the manifest
already carries the installed CLI version and the published schema URNs,
consumers should read those fields rather than assuming a fixed layout across
unrelated releases.
