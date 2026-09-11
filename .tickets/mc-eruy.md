---
id: mc-eruy
status: open
deps: [mc-h3cl]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [p3, transactions, rules, read-only, automation]
---
# Add read-only transaction rule inspection

Expose configured transaction rules so users can inspect automatic categorization and other recurring behavior without opening the web interface. This supports diagnosis and policy review but does not claim to reproduce or simulate the service's final rule engine.

## Design

Add `monarch transactions rules list` as a read-only command backed by a rules service and transformer. Require the first stable `monarchmoneycommunity` release containing `get_transaction_rules()`; declare its exact minimum version in project metadata and client-interface tests. Do not depend on an unreleased branch or add command-local raw GraphQL as a fallback.

Normalize each rule into a stable object containing `id`, nullable `order`, ordered `criteria`, ordered `actions`, nullable `recent_application_count`, and nullable `last_applied_at`. Criteria and actions are discriminated objects with a stable CLI `type` plus the known fields for that type. Preserve opaque IDs and unknown operator, enum, and scalar values without relabeling them. Do not resolve category/account IDs through extra requests or imply that similarly named arrays are equivalent unless the payload explicitly establishes that relationship.

The known GraphQL query selects a fixed set of fields. Therefore the CLI cannot preserve a newly added server field that the upstream query does not request. A rule with data outside all recognized selected criteria/actions, or a recognized container with an unsupported shape, is represented explicitly as unsupported rather than silently appearing empty. Entirely new upstream fields require an upstream query and contract update; this ticket does not promise impossible discovery of unselected GraphQL fields.

Preserve the effective rule order returned by the upstream method and expose each rule's `order` value; do not locally sort or invent direction/tie semantics. Repeated serialization of the same response must be deterministic. The known v1 payload has no rule name or enabled/disabled status, so normalized output must not fabricate either. If a future compatible upstream release adds those fields, adopting them requires an explicit contract review.

JSON and compact/NDJSON output retain the complete normalized nested structure. Human-readable plain/table output uses deterministic concise criterion/action summaries without losing rule identity or order. CSV, if offered, is explicitly a summary representation with documented columns rather than a serialization of the nested contract. Raw mode may return the untouched upstream payload and is documented as unstable.

Editing, creating, deleting, enabling/disabling, reordering, applying, or simulating rules is out of scope. `recent_application_count` and `last_applied_at` are historical metadata only and must not be presented as proof that a particular transaction was changed by a rule.

## Key Decisions

- **Stable upstream method only.** Use a released `get_transaction_rules()` surface, not ad hoc GraphQL in command code.
- **Discriminated normalized collections.** Criteria and actions use explicit CLI type labels while preserving unknown selected values.
- **GraphQL limitations are honest.** Unselected future fields cannot be preserved; unsupported selected shapes remain visible.
- **Upstream order is authoritative.** Preserve response order and expose `order` without guessing sort direction or tie behavior.
- **No fabricated name/status.** The known response exposes neither.
- **Inspection is not simulation.** Historical application metadata does not explain a specific transaction conclusively.

## Acceptance Criteria

- [ ] `monarch transactions rules list` lists rules in the effective order returned upstream and preserves nullable `order` without local reordering or invented tie semantics.
- [ ] Every normalized rule has stable `id`, `order`, `criteria`, `actions`, `recent_application_count`, and `last_applied_at` fields with documented types and nullability.
- [ ] Known merchant, amount/range, category-ID, and account-ID criteria plus known merchant/category/tag/goal/review/notification/hide/split actions normalize into documented discriminated objects.
- [ ] Opaque IDs and unknown selected operator, enum, boolean, and scalar values remain visible without being dropped, coerced into a known meaning, or causing a crash.
- [ ] Recognized containers with unsupported shapes and rules with no recognizable selected criteria/actions are explicitly marked unsupported rather than presented misleadingly as ordinary empty rules.
- [ ] Documentation states that entirely new GraphQL fields are unavailable until the upstream query selects them; the CLI does not claim to preserve data it never received.
- [ ] No rule name, enabled state, disabled state, match result, or transaction-level causality is fabricated from the known v1 payload.
- [ ] Empty lists, missing/null containers, partial rules, malformed entries, duplicate/missing/null `order`, and malformed roots have documented deterministic behavior or typed errors under mc-h3cl.
- [ ] JSON and compact/NDJSON preserve the complete nested contract; plain/table output provides legible deterministic summaries; CSV is either a documented summary or explicitly unsupported; raw output, if requested, remains untouched and unstable.
- [ ] The adapter/service/transformer boundary isolates dependency response shapes, performs no mutation, and makes no additional name-resolution calls.
- [ ] Tests cover every representative criterion/action family, nested split/range data, unknown selected values, unsupported shapes, upstream ordering, empty/null/partial/malformed payloads, all supported formats, raw passthrough, authentication/API errors, and command discovery.
- [ ] The exact stable upstream version containing `get_transaction_rules()` is declared in project metadata, lock data, and client-interface tests; no development-branch or command-local raw-GraphQL fallback is used.
- [ ] User-facing documentation explains inspection limits, ordering, unsupported data, unstable raw output, and the lack of simulation/causality claims; repository verification passes.
