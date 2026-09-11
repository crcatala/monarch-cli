---
id: mc-82kf
status: open
deps: [mc-k48z, mc-2btg]
links: []
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

Design explicit command metadata as the source of truth instead of inferring safety or behavior from command names. The manifest should be deterministic, versioned, side-effect free, and generated from the same registration or policy structures used by the CLI. It should distinguish local state changes, remote mutations, read-only operations, interactive requirements, stable versus raw output, and feature availability. Avoid coupling the public contract to unstable framework internals; include compatibility tests across the supported dependency range.

## Acceptance Criteria

- [ ] A side-effect-free command emits a documented, versioned JSON capabilities manifest.
- [ ] The manifest deterministically describes command paths, arguments, options, required inputs, and supported output modes.
- [ ] Read-only operations, remote mutations, local state changes, destructive operations, and potentially interactive commands are classified through explicit metadata rather than name heuristics.
- [ ] Mutation authorization requirements and non-interactive behavior are represented accurately.
- [ ] Stable normalized output and explicitly unstable/raw output are distinguishable.
- [ ] Manifest ordering and serialization are deterministic across repeated runs.
- [ ] Generating the manifest performs no authentication, network request, prompt, config write, or other side effect.
- [ ] Tests fail when registered commands are missing metadata or when metadata disagrees with shared execution policy.
- [ ] Compatibility tests cover supported CLI-framework versions and prevent an apparently successful empty manifest.
- [ ] User-facing and integration documentation and repository verification are complete.

