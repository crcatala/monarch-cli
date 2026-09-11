---
id: mc-87ez
status: open
deps: [mc-k48z, mc-ik8o, mc-hszv]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, transactions, tags, mutations, safety]
---
# Add safe transaction tag workflows

Support reusable transaction classification directly from the CLI. Users and automated workflows need to discover available tags, inspect existing assignments, and deliberately change them without accidentally replacing unrelated metadata. Tag writes alter financial records and therefore must build on the shared mutation authorization and execution contracts.

## Design

Treat tags as a transaction subresource with read operations available independently of mutation authorization. Define separate, unambiguous semantics for replacing the complete tag set versus adding, removing, or clearing tags. Prefer commands that make those distinctions obvious rather than a single overloaded operation. Provide deterministic post-operation results, use the shared mutation outcome envelope, and do not imply atomicity when a workflow requires multiple remote steps.

## Acceptance Criteria

- [ ] Users can list available tags and inspect the tags assigned to a transaction without mutation authorization.
- [ ] Authorized users can create a tag with locally validated required fields.
- [ ] Authorized users can replace, add, remove, or clear transaction tags with unambiguous documented semantics.
- [ ] Add/remove operations preserve unrelated existing tags and handle duplicate requested IDs deterministically.
- [ ] Invalid tag IDs, names, colors, empty requests, and conflicting options fail before mutation where they can be detected locally.
- [ ] Every write is blocked by default and uses the shared mutation authorization and retry-safe execution policies.
- [ ] Mutation responses use the shared stable outcome envelope and represent partial or ambiguous outcomes honestly.
- [ ] Read-after-write verification is performed or clearly supported where it improves safety without masking failure.
- [ ] Unit/CLI tests cover read paths, every mutation guard, replacement/merge/removal semantics, partial failures, and output modes.
- [ ] User-facing safety documentation and repository verification are complete.

