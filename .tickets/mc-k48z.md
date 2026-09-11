---
id: mc-k48z
status: open
deps: []
links: []
created: 2026-09-11T01:15:13Z
type: feature
priority: 0
assignee: cc-vps
parent: mc-cr09
tags: [p0, safety, mutations, cli, agents]
---
# Establish a centralized read-only-by-default mutation policy

Protect remote financial and service state by making the CLI read-only unless the caller explicitly authorizes mutations for that invocation. Today safeguards are command-specific and can be bypassed as the command surface grows. Humans and automated agents need one predictable contract that distinguishes reads, previews, remote mutations, local credential changes, and destructive operations.

The goal is a single enforceable trust boundary that future commands inherit automatically, not a collection of ad hoc confirmation checks.

## Design

Inventory every registered command and give it explicit operation metadata. A command may declare more than one effect when an invocation crosses boundaries. The initial effect taxonomy is:

- `read_only`: no local or remote state change.
- `preview`: a validated invocation that performs no state change, such as `--dry-run`.
- `remote_authentication`: establishes or changes a remote authentication/session relationship without changing financial data.
- `remote_mutation`: creates, updates, deletes, uploads, refreshes, or otherwise initiates a state-changing remote financial or service action.
- `local_credential_change`: writes or removes local authentication state.

`--allow-mutations` is required when an invocation's effect set contains `remote_mutation`; other effects do not imply authorization. `auth login` declares both `remote_authentication` and `local_credential_change`, while `auth logout` declares `local_credential_change`. Both remain available without the flag so users can authenticate and recover access.

Add a global, CLI-only `--allow-mutations` option. It is false by default, applies only to the current process invocation, and must appear in the documented global-option position before the command path. Do not support persistent configuration or an environment variable for mutation authorization.

Use two coordinated enforcement layers:

1. Registration metadata makes the full command inventory explicit and testable.
2. A shared remote-operation boundary requires an explicit operation descriptor before executing a mutation.

Do not infer effect from CLI command names, upstream client method names, or GraphQL operation names. Tests must fail when a registered command lacks metadata or when a remote mutation can use a read-only execution path.

A statically mutating command may declare a validated preview mode. The policy may classify that parsed invocation as `preview` only after confirming the no-effect option, and must still prevent API/client mutation calls. Mutation authorization must be checked before authentication lookup, API-client creation, destructive confirmation, or any other prompt. Destructive confirmation or `--yes` is a separate second layer applied only after mutation authorization succeeds.

The shared operation descriptor established here is consumed by `mc-t9o7` for retry and ambiguity behavior. Future command classes can extend the taxonomy when they are introduced rather than adding speculative categories here.

## Key Decisions

- **Gate remote financial/service mutations, not credential recovery.** Login declares both remote-authentication and local-credential effects, but login and logout do not require `--allow-mutations`.
- **Include service actions such as refresh.** Read-only means observationally read-only, not merely “does not directly edit a transaction.”
- **Per-invocation authorization only.** Persistent or inherited authorization would make accidental mutation too easy.
- **Preview remains available safely.** A proven no-effect dry run does not require mutation authorization.
- **Authorize before prompting.** A blocked destructive operation must not prompt for confirmation before reporting that mutation authorization is missing.
- **Use defense in depth.** Registration metadata provides discoverability and exhaustiveness; the shared execution boundary prevents direct-client bypasses.

## Acceptance Criteria

- [ ] Every registered command has explicit reviewed operation metadata using one or more values from the shared effect taxonomy.
- [ ] Policy tests cover a synthetic or real multi-effect command so metadata and authorization do not silently collapse to a single effect.
- [ ] Current `transactions update`, `transactions batch-update`, and `accounts refresh` invocations include `remote_mutation` in their effect sets.
- [ ] `auth login` declares `remote_authentication` and `local_credential_change`; `auth logout` declares `local_credential_change`; both remain usable without `--allow-mutations`.
- [ ] Read-only commands remain usable without mutation authorization.
- [ ] Validated transaction `--dry-run` invocations remain usable without mutation authorization and cannot create an authenticated client or make a mutation API call.
- [ ] The CLI defaults to read-only and blocks every remote mutation before authentication lookup, client creation, API calls, confirmation, or other prompts.
- [ ] `monarch --allow-mutations …` authorizes remote mutations for that invocation only; no config-file or environment authorization is supported.
- [ ] Destructive operations require their additional confirmation or `--yes` layer after mutation authorization succeeds.
- [ ] Missing mutation authorization produces `MUTATION_BLOCKED`, exits with code `3`, writes no success payload to stdout, and provides an actionable example on stderr.
- [ ] JSON/compact or non-TTY failures emit one valid structured error without prose or ANSI escapes; interactive human-readable failures are concise and deterministic.
- [ ] Mutation classification is explicit metadata or an explicit parsed-operation descriptor, never a command-name, method-name, or GraphQL-name heuristic.
- [ ] The shared remote-operation boundary requires explicit effect metadata and cannot silently execute a mutation through the read executor.
- [ ] Tests fail if any registered command lacks metadata, if metadata and execution policy disagree, or if a remote mutation bypasses authorization.
- [ ] Tests prove every current remote mutation is blocked by default, enabled only with explicit authorization, and makes no API call while blocked.
- [ ] Tests prove authorization does not persist between CLI invocations and that blocked destructive commands do not prompt.
- [ ] Help and user documentation explain global flag placement, the effect taxonomy, preview behavior, credential-command treatment, and the two-layer safety model.
- [ ] Repository verification passes.
