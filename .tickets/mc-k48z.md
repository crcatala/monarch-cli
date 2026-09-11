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

Protect financial state by making the CLI read-only unless the caller explicitly authorizes mutations. Today, safeguards are command-specific and can be bypassed as the command surface grows. Humans and automated agents need one predictable contract that distinguishes read operations from creates, updates, deletes, uploads, refreshes, and arbitrary API mutations.

The goal is a single enforceable trust boundary that future commands inherit automatically, not a collection of ad hoc confirmation checks.

## Design

Start by inventorying every existing command and explicitly classifying whether it can change remote or local security-sensitive state. Design a centralized policy that can be applied declaratively at command registration or a shared command/service boundary. Do not infer mutation status from command names.

Provide an explicit opt-in such as a global `--allow-mutations`, with safe behavior in interactive and non-interactive execution. Destructive confirmations such as `--yes` remain a separate second layer where appropriate. The policy should be reusable by a future raw API command, which must classify parsed operations and reject mutations by default; implementing that raw API command is not required here. Avoid relying solely on documentation or individual command authors remembering to call a guard.

## Acceptance Criteria

- [ ] Every existing command has an explicit, reviewed read/mutation classification.
- [ ] The CLI defaults to read-only and blocks every classified mutation before making an API call.
- [ ] A documented explicit opt-in enables mutation commands for that invocation.
- [ ] Destructive operations still require their additional confirmation mechanism where applicable.
- [ ] Interactive, non-interactive, JSON, and human-readable failures are deterministic and return a documented non-zero exit code.
- [ ] Mutation classification is explicit metadata or equivalent policy, not command-name heuristics.
- [ ] Shared policy can classify and guard future parsed API operations, including raw GraphQL mutations.
- [ ] Tests prove each existing mutation is blocked by default and enabled only with explicit authorization.
- [ ] Tests prove read-only commands remain usable without mutation authorization.
- [ ] Help and user documentation clearly explain the safety model.

