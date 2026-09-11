---
id: mc-82kf
status: open
deps: [mc-k48z, mc-2btg, mc-43s0, mc-cpzi]
links: [mc-cpzi]
created: 2026-09-11T01:47:48Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p3, capabilities, automation, contracts, agent-ux]
---
# Publish a deterministic CLI capabilities manifest

Provide a machine-readable inventory of the installed CLI so automation can discover commands, arguments, options, output support, safety requirements, and contract versions without scraping styled help text. This enables agents and integrations to adapt to the actual installed version and avoid guessing whether an operation is available or state-changing.

## Design

Add a side-effect-free command that emits a versioned JSON manifest. Explicit command and operation metadata is authoritative for effects, safety policy, interactivity, feature availability, output stability, and contract references; none of those properties may be inferred from command, framework, upstream method, or GraphQL names.

Framework introspection may enumerate registered command paths, arguments, and options, but the public manifest shape is owned by CLI code and protected by one canonical fixture test rather than exposing Typer internals. Completeness checks compare the registered command tree with explicit metadata and reject an empty or partial inventory.

Model output behavior accurately: global formats and quiet behavior are distinct from command-specific support such as NDJSON and raw passthrough. Raw output is explicitly unstable. Stable schema identifiers and contract versions come from the lightweight mapping published by `mc-cpzi` rather than duplicated constants. Compatibility testing is limited to the supported Typer range established by `mc-43s0`; this ticket does not widen that range.

## Key Decisions

- **Explicit metadata owns behavior.** Introspection discovers syntax only; it never determines whether an operation is safe or state-changing.
- **Schemas have one lightweight mapping.** `mc-cpzi` owns stable schema identifiers and versions in an ordinary module-level mapping; this ticket consumes it.
- **Output support is per command.** Global rendering formats, quiet output, NDJSON, and raw passthrough are represented separately.
- **Framework support is bounded.** Compatibility tests target only the dependency range established by `mc-43s0`.

## Acceptance Criteria

- [ ] A side-effect-free command emits one documented, versioned JSON capabilities manifest.
- [ ] The manifest deterministically describes every command path, argument, option, required input, and relevant default without exposing framework-internal object shapes.
- [ ] Read-only, preview, remote authentication, remote mutation, local credential/config changes, destructive, and potentially interactive behavior is classified through explicit shared metadata, including future taxonomy extensions.
- [ ] Mutation authorization, destructive confirmation, and non-interactive requirements are represented accurately and separately.
- [ ] Global output formats and quiet behavior are distinct from per-command NDJSON and raw support; stable normalized output and unstable raw passthrough are clearly identified.
- [ ] Stable schema identifiers and contract versions exactly match the mapping published by `mc-cpzi`.
- [ ] One canonical fixture test verifies stable manifest shape, ordering, byte-for-byte serialization, and protection from framework-introspection drift across repeated runs.
- [ ] Generation performs no authentication lookup, client construction, network request, prompt, config/session creation or write, or other local/remote mutation.
- [ ] Completeness tests fail when a registered command is missing metadata, metadata disagrees with shared execution policy, schema references are unknown, or the generated inventory is unexpectedly empty or partial.
- [ ] Compatibility tests cover the supported Typer range established by `mc-43s0` without widening dependency constraints.
- [ ] User-facing and integration documentation explains discovery, versioning, stability, and raw-output caveats; repository verification passes.
