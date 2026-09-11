---
id: mc-wtfb
status: open
deps: []
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p3, config, ux, automation]
---
# Add first-class configuration management commands

Give users and automated workflows a supported way to inspect and manage effective CLI configuration without manually locating or editing TOML. This makes configuration discoverable, reduces malformed-file errors, and lets diagnostics explain why behavior differs across machines or execution contexts. The command surface must manage CLI preferences only; credentials and other secrets are explicitly out of scope.

## Design

Design a cohesive config command group for listing supported settings, reading one setting, setting a value, and unsetting a persisted override. Reuse the existing configuration loader and validation rules rather than creating a second configuration model. Make the distinction between persisted values, environment overrides, CLI overrides, defaults, and the final effective value clear. Writes should be atomic and preserve unrelated valid settings. Agents should evaluate whether a small schema/registry of supported keys can drive validation, help text, provenance, and future capability metadata.

## Acceptance Criteria

- [ ] Users can list supported configuration keys and inspect the effective configuration in both human-readable and JSON forms.
- [ ] Users can get one setting and see its effective value and source/provenance without exposing credentials or secrets.
- [ ] Users can set and unset supported persisted settings through validated commands.
- [ ] Unknown keys, invalid values, malformed booleans/numbers/enums, and non-writable config locations fail with actionable errors and no partial write.
- [ ] Environment and command-line overrides are not accidentally persisted, and precedence behavior is documented and tested.
- [ ] Writes are atomic, preserve unrelated settings, and use appropriate file permissions.
- [ ] Non-interactive invocation never prompts and has deterministic exit codes and machine-readable errors.
- [ ] Unit and CLI tests cover defaults, persisted values, overrides, unset behavior, corrupt input, and write failures.
- [ ] User-facing documentation and repository verification are complete.

