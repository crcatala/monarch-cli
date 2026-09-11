---
id: mc-2btg
status: open
deps: [mc-k48z]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 0
assignee: cc-vps
parent: mc-cr09
tags: [p0, automation, non-interactive, cli, agents]
---
# Define deterministic non-interactive CLI behavior

Ensure every command can run safely in CI, scripts, and agent workflows without hanging on an unexpected prompt. Automated callers need a reliable way to declare that input is unavailable and receive a structured, actionable failure before authentication, confirmation, or setup code attempts to read from stdin.

## Design

Introduce one shared non-interactive policy driven by a global flag and documented environment/config behavior. Inventory every current prompt site and migrate it to one shared guard; document that future prompts must use the same guard. Keep mutation authorization and destructive confirmation as separate safety concepts: non-interactive mode controls whether prompting is allowed, not whether a mutation is authorized. Define a stable exit code and preserve stdout/stderr contracts for JSON and human-readable modes.

## Key Decisions

- **P0 foundation.** Prompt safety is required before the CLI can be considered safe for unattended agents and CI, and it completes the execution-mode contract established by `mc-k48z`.
- **Separate policies.** Non-interactive mode controls whether input may be requested; it does not authorize mutations or satisfy destructive confirmation.
- **Fail before reading input.** Policy checks happen before `stdin`, `/dev/tty`, password, MFA, storage-choice, or confirmation reads.

## Acceptance Criteria

- [ ] A global non-interactive mode is available through a documented CLI flag and automation-friendly configuration source.
- [ ] Every current prompt site uses the shared policy before attempting input, and contributor guidance requires future prompts to use the same guard.
- [ ] A blocked prompt fails promptly with a stable non-zero exit code and identifies the missing input and non-interactive remedy.
- [ ] JSON mode emits a valid structured error on the documented stream with no surrounding prose or ANSI escapes.
- [ ] Human-readable mode remains concise and actionable.
- [ ] Non-interactive mode does not bypass mutation authorization or destructive confirmation requirements.
- [ ] Interactive behavior remains unchanged when non-interactive mode is not enabled.
- [ ] Tests cover login, confirmation-required operations, stdin-related edge cases, CI/environment behavior, and output modes.
- [ ] Repository verification passes.

