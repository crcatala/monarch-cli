---
id: mc-qv0q
status: open
deps: []
links: []
created: 2026-09-19T01:19:38Z
type: epic
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [roadmap, cli, ux, breaking-change, safety, automation]
---
# Major-release CLI UX consistency and safety hardening

Coordinate the breaking CLI improvements planned for the next breaking release so commands have predictable invocation patterns for both humans and automation. The current command surface has good safety foundations, but several commands still mix positional mutation targets, root-only and leaf-local flags behave inconsistently, some mutations lack previews, and a few validation/error/help paths do not clearly communicate their contracts.

Release context: the v0.1.0 surface **is** published (PyPI upload and GitHub release on 2026-01-19), so this is not an unreleased prototype. The project is still 0.x/Beta, semver permits breaking changes in a 0.x minor release, and the team accepts that existing positional forms and option aliases need no compatibility shims. The target is the next breaking release (`0.2.0`, unless the project explicitly designates this as the 1.0.0 surface stabilization); either way the breaking changes must be documented for users through a CHANGELOG breaking-changes section and README migration notes. The goal is a coherent CLI style rather than preserving every historical invocation.

## Design

## Style decisions

- Keep positional identifiers for simple read-only single-resource commands where there is no ambiguity.
- Use explicit target options for mutations, especially when a command accepts more than one resource/value concept.
- Use repeatable options for multiple values instead of comma-delimited strings.
- Use separate typed options when a value may be an opaque ID or a human name.
- Keep global options before the command path; reconcile all examples with that grammar.
- Explicit machine-readable output selections (`--json`, `--format`, `--ndjson`) are unaffected by TTY state; default rendering may stay TTY-aware.
- Preserve the existing mutation authorization, confirmation, ambiguity, verification, and no-automatic-retry policies.
- One verb and one option name per concept: no compatibility aliases or shims for the removed forms.

## Cross-cutting decisions

- **Preview rule.** A `--dry-run` preview may perform read-only work (including authentication and reads) but never calls a mutation endpoint, never requires `--allow-mutations`, and never prompts for confirmation. Each command's help states what a preview reads. Previews emit a minimal `status: "dry_run"` result with the operation and target; they are explicitly distinct from `mutation-outcome.v1` and are not registered as a second stable schema family.
- **Validation order.** Input validation precedes mutation authorization; authorization always precedes authentication lookup, client creation, and any prompt.
- **Mutation output.** Every remote mutation emits the JSON `mutation-outcome.v1` envelope on stdout regardless of TTY state. `--quiet` and any explicit `--format` other than `json` never swallow or re-render a mutation outcome or preview.
- **No generic mutation framework.** Extract only the duplicated command-layer primitives (outcome emission, destructive confirmation, transaction-ID validation, payload container/error parsing, object coercion). Do not build a generic multi-stage mutation pipeline.
- **Applies to upcoming mutations.** The target, multi-value, preview, and output conventions apply to the transaction mutation tickets still open under `mc-cr09` (`mc-2v9a`, `mc-bf8f`, `mc-e49c`), which now reference this epic.

Existing related work should be incorporated rather than duplicated: `mc-46gq` covers the tag assignment redesign and `mc-4z49` covers help/example auditing.

## Acceptance Criteria

- [ ] The next breaking release's invocation grammar, preview/output contracts, and breaking-change policy are documented (README migration notes plus a CHANGELOG breaking-changes section for the target version).
- [ ] Child work establishes a consistent mutation-target, multi-value, output, preview, and validation style across affected commands and the open `mc-cr09` mutation tickets.
- [ ] Existing tag redesign work is tracked under this epic and does not retain positional or alias compatibility.
- [ ] Existing help/documentation polish is reconciled with the new syntax and global-option grammar.
- [ ] Safety behavior remains explicit: remote writes require `--allow-mutations`, confirmations remain separate from authorization, and ambiguous writes are never silently retried.
- [ ] Machine-readable output and exit-code behavior remain stable, or are deliberately documented for the target release; explicit machine-readable selections are unaffected by TTY state.
- [ ] `--quiet` never silently discards mutation outcomes or previews.
- [ ] Only the duplicated mutation primitives are extracted; no generic mutation pipeline is introduced.
- [ ] Unit/CLI tests and repository verification cover the new invocation contracts and representative failure paths.
