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

Several remote mutation commands use positional transaction identifiers even though their purpose is to change remote state. This makes generated commands less self-describing and creates the same class of ambiguity that motivated the tag redesign. The next major release does not need to preserve these positional forms.

Standardize mutation target selection without making simple read-only commands unnecessarily verbose. `accounts refresh` already provides the desired repeatable-option model.

## Design

Use these canonical mutation forms:

```text
transactions update --transaction-id TXN_ID [change options]
transactions batch-update --transaction-id TXN_ID [--transaction-id TXN_ID ...] [--stdin] [change options]
transactions splits replace --transaction-id TXN_ID [--splits-json ... | --splits-file ...]
transactions splits clear --transaction-id TXN_ID
```

Remove positional transaction IDs from these mutation commands rather than retaining compatibility aliases. Keep positional IDs for read-only single-resource commands such as `transactions get`, `transactions tags show`, `transactions splits show`, and `accounts history` unless a separate consistency decision changes that policy.

Batch input may combine repeatable `--transaction-id` and `--stdin`; normalize/deduplicate IDs in first-seen order so a transaction cannot be updated twice accidentally. Preserve the existing mutation authorization, confirmation, concurrency, outcome, ambiguity, and verification policies.

## Acceptance Criteria

- [ ] `transactions update` requires `--transaction-id` and no longer accepts a positional transaction ID.
- [ ] `transactions batch-update` accepts repeatable `--transaction-id` options and no longer accepts positional transaction IDs.
- [ ] `transactions splits replace` and `transactions splits clear` require `--transaction-id` and no longer accept positional transaction IDs.
- [ ] Batch mode still supports `--stdin`; positional and stdin sources are replaced by repeatable options plus stdin, and combined input is explicitly documented.
- [ ] Batch IDs are deduplicated in first-seen order before any mutation attempt, with tests covering duplicates from both options and stdin.
- [ ] Missing target IDs, empty IDs, and missing batch input produce structured pre-execution validation errors before authentication or mutation.
- [ ] Existing mutation safety, dry-run behavior, outcome envelopes, ambiguity handling, and API payloads remain correct.
- [ ] Help, README examples, tests, and shell completion reflect the breaking option-based syntax.
- [ ] Repository verification passes.

