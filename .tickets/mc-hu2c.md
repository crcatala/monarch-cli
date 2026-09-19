---
id: mc-hu2c
status: open
deps: []
links: []
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

Keep global options before the command path and reconcile README/docstring/help examples with that grammar. Keep leaf-local `--json` convenience options where they already exist, but route both root and local selections through one effective output-resolution path.

Root `--json` must affect structured commands, including successful `auth status` and `auth ping`; human-only commands such as `auth login`, `auth doctor`, and `auth setup` should explicitly document their human-oriented behavior rather than silently pretending to support every output mode.

Remote mutation commands should always emit the `mutation-outcome.v1` envelope as JSON on stdout regardless of TTY state. Progress and diagnostics remain on stderr. Mutation output should not be transformed into plain/table/CSV output.

## Acceptance Criteria

- [ ] The documented grammar is `monarch [GLOBAL OPTIONS] GROUP COMMAND [COMMAND OPTIONS]`, and all repository examples use it correctly.
- [ ] Root global options such as `--quiet`, `--timeout`, `--no-color`, `--verbose`, `--debug`, `--allow-mutations`, `--yes`, and `--non-interactive` are documented with correct placement.
- [ ] Root `--json` and command-local `--json` resolve through the same effective output policy.
- [ ] `monarch --json auth status` produces the same structured JSON contract as `monarch auth status --json`.
- [ ] `monarch --json auth ping` produces structured JSON on successful connectivity, while human-only authentication/setup commands have explicit documented output limitations.
- [ ] All remote mutation commands emit valid JSON `mutation-outcome.v1` on stdout even when stdout is a TTY; progress and diagnostics remain on stderr.
- [ ] Mutation output cannot accidentally be rendered as plain, table, CSV, or compact output in a way that violates the outcome contract.
- [ ] Piped read output, `--quiet`, NDJSON, and local format shortcuts retain their documented behavior.
- [ ] Tests cover root/local JSON equivalence, TTY and non-TTY mutation output, stderr separation, and representative global-option placement failures/successes.
- [ ] Help/documentation work is reconciled with `mc-4z49`, and repository verification passes.

