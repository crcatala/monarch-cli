---
id: mc-hu2c
status: in_progress
deps: []
links: [mc-s6s6]
created: 2026-09-19T01:19:38Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-qv0q
tags: [cli, output, automation, mutations, breaking-change, ux]
---
# Make global options and machine-readable output behavior consistent

The CLI has both root-level and command-local output flags, but they are not fully equivalent. Root global options must precede the command path, several documentation examples place them afterward, and manually formatted authentication commands do not consistently honor root `--json`. Mutation outcome documentation also describes a machine-readable contract while the generic formatter can render outcomes differently in an interactive TTY.

Make the invocation grammar and output contract predictable for humans, shell pipelines, and agents without weakening existing safety behavior.

## Design

Keep global options before the command path and reconcile README/docstring/help examples with that grammar. Keep leaf-local `--json` convenience options where they already exist.

Document one precedence rule instead of adding an output-policy abstraction: an explicit leaf selection (`-f/--format`, local `--json`, `--ndjson`) overrides the root default; root `--json` supplies the default for structured commands; without either, rendering stays TTY-aware (plain on a TTY, JSON when piped). `auth status` and `auth ping` must stop hand-rolling their own output and resolve output through the same effective value, so `monarch --json auth status` matches `monarch auth status --json`. Human-oriented commands such as `auth login`, `auth doctor`, and `auth setup` (and `auth logout`) are documented as human-oriented; the CLI does not add a new unsupported-output error code for them, and `--non-interactive` remains the automation-safe failure mode for anything that would prompt.

Remote mutation commands always emit the `mutation-outcome.v1` envelope as JSON on stdout regardless of TTY state, and the same applies to dry-run previews. Progress and diagnostics remain on stderr. Implement this once: add a shared `emit_mutation_outcome()` helper (used by every mutation command and by preview emission) that owns forced JSON output, the status-to-exit-code mapping, and rejection of output selections that would violate the contract. `--quiet` and any explicit `-f/--format` other than `json` (plain, table, csv, compact) on a mutation or preview command fail with a structured input error instead of silently swallowing or re-rendering the result; `--json`/`-f json` are accepted as already satisfied. Update `docs/mutation-outcomes.md` accordingly (TTY independence, the added `transactions.tags.add` operation, previews remaining distinct from the envelope).

Do not build a generic output-resolution framework; the behavior above plus the existing `output()`/`get_default_format()` path is sufficient.

## Acceptance Criteria

- [ ] The documented grammar is `monarch [GLOBAL OPTIONS] GROUP COMMAND [COMMAND OPTIONS]`, and all repository examples use it correctly (including the currently broken README examples that place `--timeout`, `--no-color`, `--verbose`, and `--quiet` after the command path).
- [ ] Root global options such as `--quiet`, `--timeout`, `--no-color`, `--verbose`, `--debug`, `--allow-mutations`, `--yes`, and `--non-interactive` are documented with correct placement, and the README global-options table no longer omits `--timeout` and `--yes`.
- [ ] The documented precedence is: explicit leaf output selection overrides the root default, which otherwise stays TTY-aware; root `--json` and command-local `--json` produce identical output.
- [ ] `monarch --json auth status` produces the same structured JSON contract as `monarch auth status --json`, and `monarch --json auth ping` produces structured JSON on successful connectivity.
- [ ] Human-only authentication commands have explicit documented output limitations; no new output-mode error code is introduced.
- [ ] All remote mutation commands and dry-run previews emit valid JSON on stdout even when stdout is a TTY; progress and diagnostics remain on stderr.
- [ ] A single shared `emit_mutation_outcome()` helper owns mutation/preview emission; `--quiet` and any `-f/--format` other than `json` on a mutation or preview fail with a structured input error rather than silently producing no output or a re-rendered result.
- [ ] `docs/mutation-outcomes.md` documents TTY-independent emission, includes `transactions.tags.add`, and states that dry-run previews are not part of the envelope.
- [ ] Piped read output, `--quiet` (for id-bearing read output), NDJSON, and local format shortcuts retain their documented behavior.
- [ ] Tests cover root/local JSON equivalence, TTY and non-TTY mutation output, stderr separation, quiet/format rejection on mutations, and global-option placement; the misnamed `test_global_options_after_subcommand` test is repurposed to assert real global-option placement behavior.
- [ ] Help/documentation work is reconciled with `mc-4z49`, and repository verification passes.
