---
id: mc-7xfl
status: open
deps: [mc-h3cl]
links: [mc-4edf]
created: 2026-09-11T01:47:48Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, accounts, discovery, read-only, automation]
---
# Add read-only account type discovery

Expose the valid account groups, types, and subtypes accepted by account workflows. Today callers must guess identifiers or obtain them outside the CLI, which makes manual-account automation brittle and increases validation failures. A read-only discovery command gives humans and agents authoritative values before they construct later operations.

## Design

Add the capability under the accounts domain and normalize the supported type hierarchy into a stable CLI contract. This is a P1 prerequisite for the account-type filter validation in `mc-4edf`, so it must land before that ticket rather than remaining later-stage automation ergonomics. Preserve machine-usable identifiers and human-readable labels, define ordering, and handle partially populated or evolving upstream options without leaking raw response structure as the default. Keep dependency-specific calls and shapes behind the adapter/service boundary.

## Key Decisions

- **Promoted to P1 prerequisite.** `mc-4edf` consumes this normalized hierarchy for account-type filter validation and depends on this ticket explicitly.

## Acceptance Criteria

- [ ] A discoverable read-only command lists supported account groups/types and their subtypes.
- [ ] Normalized output preserves the identifiers required by account workflows and useful display labels/descriptions when available.
- [ ] Parent/child relationships and deterministic ordering are documented and stable.
- [ ] JSON and human-readable output are useful; optional raw output, if offered, is explicit and leaves the source payload untouched.
- [ ] Empty, null, partial, unknown, and newly introduced option fields do not crash the command or invent values.
- [ ] The command performs no remote mutation and makes no direct dependency import from the command handler.
- [ ] Tests cover API mapping, normalization, ordering, empty/partial responses, formats, and errors.
- [ ] The minimum compatible dependency version is declared when required.
- [ ] User-facing documentation and repository verification are complete.

