---
id: mc-bf8f
status: open
deps: [mc-iarh, mc-k48z, mc-ik8o, mc-2btg]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [p3, transactions, household, ownership, mutation, safety]
---
# Add guarded transaction ownership updates

Allow shared households to assign one transaction to a member or return it to Shared ownership through an explicit, auditable CLI workflow. Incorrect assignment changes reporting and household interpretation, so the workflow must build on member discovery and the common mutation safety, ambiguity, and outcome policies.

## Design

Add the focused command `monarch transactions ownership set TRANSACTION_ID` with exactly one of `--member MEMBER_ID` or `--shared`. Do not add ownership flags to the general `transactions update` command: a dedicated operation keeps authorization, preview, verification, and recovery semantics independent from unrelated transaction edits. The stable operation identifier is `transactions.ownership.set`.

The CLI options never expose the upstream empty-string/null wire convention. `--member` supplies a non-empty opaque member ID; `--shared` deliberately requests Shared ownership. Omitting both, supplying both, or supplying an empty member ID fails validation before authentication, client construction, or any request. This ticket does not define a separate “unassigned” state because the verified upstream contract distinguishes only a member assignment and Shared ownership.

Member IDs are normally obtained from `monarch household members list` in mc-iarh. Dry-run validates only local syntax and mutual exclusivity and clearly states that remote membership was not checked; it makes no authentication lookup, client construction, discovery call, or mutation request. Normal execution performs a bounded household-member lookup before mutation for `--member`, but the server remains authoritative because membership can change between validation and write.

Use only a stable upstream release that provides both `get_household_members()` and `update_transaction(..., owner_user_id=...)`. The upstream adapter owns the conversion from the public `--shared` choice to the verified wire representation; command and service code never pass magic empty strings. Do not use a development branch or add command-local raw GraphQL as a fallback. Declare the exact minimum released `monarchmoneycommunity` version in project metadata and client-interface tests once that release exists.

Execution uses the shared remote-mutation boundary, no-unsafe-retry policy, deterministic non-interactive behavior, and `mutation-outcome.v1`. The upstream ownership mutation response currently does not include `ownedByUser`, so success requires a bounded transaction-detail readback. A matching member ID or verified Shared representation is succeeded; a definite mismatch is a non-successful verified outcome; mutation or verification uncertainty is surfaced through the shared ambiguity/recovery contract and is never retried blindly. The feature must not invent command-local statuses, envelopes, or exit codes.

## Key Decisions

- **Dedicated ownership command.** Ownership is not combined with amount, category, note, or other transaction edits.
- **Explicit public choices.** `--member` and `--shared` replace the upstream empty-string/null convention.
- **No invented unassigned state.** V1 supports member-owned and Shared only.
- **Preview is local.** Dry-run does not authenticate or claim that a member ID exists remotely.
- **Bounded readback is mandatory.** The known mutation response does not return ownership fields.
- **Stable upstream release required.** Development-branch support is evidence, not a compatible dependency floor.

## Acceptance Criteria

- [ ] `monarch transactions ownership set TRANSACTION_ID` accepts exactly one of non-empty `--member MEMBER_ID` or `--shared` and uses stable operation ID `transactions.ownership.set`.
- [ ] Member assignment and Shared ownership are the only public v1 states; no empty-string, null, boolean, or inferred “unassigned” option is exposed.
- [ ] Missing options, both options, and an empty member ID fail before authentication lookup, client creation, discovery, mutation, or prompting.
- [ ] Dry-run performs local validation only, makes no API/client call, states that remote membership was not validated, and emits the shared preview contract.
- [ ] Normal member assignment performs a bounded read-only household-member lookup before mutation; an unknown member produces a structured pre-execution error, while the server remains authoritative for race conditions.
- [ ] Omitting ownership options from every other transaction command never adds an ownership key or changes existing ownership.
- [ ] Execution requires per-invocation mutation authorization and uses the shared mutation executor, deterministic non-interactive behavior, retry/ambiguity policy, and `mutation-outcome.v1` without feature-local variants.
- [ ] A bounded transaction-detail readback verifies the resulting member ID or the upstream Shared representation before the command claims verified success.
- [ ] Definite readback mismatch, readback transport failure, and uncertain mutation outcomes are mapped through the shared outcome/recovery policy without unsafe automatic mutation retry.
- [ ] Tests cover member assignment, Shared ownership, missing/empty/conflicting inputs, dry-run isolation, unknown member, membership race/API rejection, blocked authorization, success readback, mismatch, transport ambiguity, machine-readable output, and human output.
- [ ] The feature requires the first stable `monarchmoneycommunity` release containing both `get_household_members()` and `owner_user_id` support; the exact floor is declared in project metadata, lock data, and client-interface tests, with no development-branch or raw-GraphQL fallback.
- [ ] User-facing documentation explains discovery, preview limitations, member versus Shared semantics, authorization, verification, and safe recovery; repository verification passes.
