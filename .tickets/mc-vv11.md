---
id: mc-vv11
status: open
deps: []
links: []
created: 2026-09-19T01:19:38Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-qv0q
tags: [transactions, mutations, cli, breaking-change, ux]
---
# Standardize explicit target options for transaction mutations

Several remote mutation commands use positional transaction identifiers even though their purpose is to change remote state. This makes generated commands less self-describing and creates the same class of ambiguity that motivated the tag redesign. The next breaking release does not need to preserve these positional forms.

Standardize mutation target selection without making simple read-only commands unnecessarily verbose. `accounts refresh` already provides the desired repeatable-option model.

## Design

Use these canonical mutation forms:

```text
transactions update --transaction-id TXN_ID [change options]
transactions batch-update --transaction-id TXN_ID [--transaction-id TXN_ID ...] [--stdin] [change options]
transactions splits replace --transaction-id TXN_ID [--splits-json ... | --splits-file ...]
transactions splits clear --transaction-id TXN_ID
```

Remove positional transaction IDs from these mutation commands rather than retaining compatibility aliases. The split source keeps exactly one name per concept: `--splits-json` and `--splits-file`; the legacy aliases (`--json-input`, `--input-json`, `--file`, `--input-file`) are removed rather than retained, for the same no-shim reason. Keep positional IDs for read-only single-resource commands such as `transactions get`, `transactions tags show`, `transactions splits show`, and `accounts history` unless a separate consistency decision changes that policy.

A removed positional form must still produce an actionable usage error that points at `--transaction-id`; the CLI never silently accepts or reinterprets a positional ID.

Batch input may combine repeatable `--transaction-id` and `--stdin`; repeatable option values are consumed first, then stdin lines, and the combined list is normalized/deduplicated in first-seen order so a transaction cannot be updated twice accidentally. Preserve the existing mutation authorization, confirmation, concurrency, outcome, ambiguity, and verification policies.

## Acceptance Criteria

- [ ] `transactions update` requires `--transaction-id` and no longer accepts a positional transaction ID.
- [ ] `transactions batch-update` accepts repeatable `--transaction-id` options and no longer accepts positional transaction IDs.
- [ ] `transactions splits replace` and `transactions splits clear` require `--transaction-id` and no longer accept positional transaction IDs.
- [ ] `transactions splits replace` accepts exactly one source name per concept (`--splits-json` or `--splits-file`); the legacy source aliases are removed.
- [ ] Removed positional forms produce an actionable usage error pointing at `--transaction-id`, and no compatibility alias or positional fallback is retained.
- [ ] Batch mode still supports `--stdin`; positional and stdin sources are replaced by repeatable options plus stdin, and combined input is explicitly documented.
- [ ] Batch IDs are deduplicated in first-seen order before any mutation attempt, with tests covering duplicates from both options and stdin.
- [ ] Missing target IDs, empty IDs, and missing batch input produce structured pre-execution validation errors before authentication or mutation.
- [ ] Batch ordering is documented and tested: repeatable option values are consumed before stdin lines, and the combined list is deduplicated in first-seen order.
- [ ] Existing mutation safety, dry-run behavior, outcome envelopes, ambiguity handling, and API payloads remain correct.
- [ ] Help, README examples, and framework parsing tests reflect the breaking option-based syntax; there are no in-repo shell-completion artifacts (Typer generates completion from registered options), so completion needs no separate update.
- [ ] Repository verification passes.

