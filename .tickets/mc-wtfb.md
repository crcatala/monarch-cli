---
id: mc-wtfb
status: open
deps: [mc-k48z, mc-2btg, mc-43s0]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p3, config, ux, automation]
---
# Add first-class configuration management commands

Give users and automated workflows a supported way to inspect and manage effective CLI configuration without manually locating or editing TOML. This makes preferences discoverable, prevents malformed writes, and explains why behavior differs across machines or execution contexts. Credentials, session data, mutation authorization, and other secrets are explicitly outside this command surface.

## Design

Add a cohesive `config` command group with `list`, `get KEY`, `set KEY VALUE`, and `unset KEY`. A mandatory setting registry is the single source for each public key, internal `Config` field, TOML key, environment variable(s), type, validator, default, description, persistability, and safety notes. It drives validation, help, provenance, and future capability metadata; do not create a second configuration model.

V1 manages the existing non-secret preferences: format, color, verbose, debug, quiet, timeout, max retries, and destructive-confirmation preference. Mutation authorization and non-interactive mode are never persisted by these commands. `config set confirm_destructive false` requires an explicit acknowledgement flag because it weakens a separate safety layer; it never grants mutation authorization.

Use `tomlkit>=0.13,<1` to edit the raw TOML document while preserving unrelated valid settings, comments, and formatting. Declare it as a direct runtime dependency and regenerate the lockfile under `mc-43s0`'s dependency rules. Writes use a same-directory temporary file, flush/close, and atomic replace. Configuration is non-secret and may use ordinary platform-appropriate readable permissions, but writing it must never loosen permissions on the shared config directory or credential files.

Read effective values through the existing layered loader, but never serialize effective configuration back to disk. Environment and CLI overrides remain transient. Writes modify only the requested persisted key in the raw document. `unset` removes only that persisted override and reveals the next effective source.

Strictness is operation-specific: `set` strictly validates the proposed value; `get/list` report actionable diagnostics for malformed existing TOML; ordinary unrelated CLI startup retains its existing lenient fallback behavior unless changed by another ticket. A malformed document is never partially repaired or overwritten by `set/unset`.

Add an explicit `local_config_change` operation effect as an extension of the shared metadata taxonomy. It does not require `--allow-mutations`, which remains reserved for remote mutations, but it is discoverable in capabilities. All config commands are non-prompting except the explicit safety acknowledgement supplied as an option, so non-interactive behavior is deterministic.

## Key Decisions

- **Registry is mandatory.** It owns names, mappings, validation, provenance, and persistence policy.
- **TOML-preserving writes.** Use bounded `tomlkit` and retain unrelated values, comments, and layout.
- **Never persist effective state.** Only the requested file override is changed; env/CLI/default values are not copied.
- **Strict management, lenient ordinary startup.** Corrupt TOML blocks management writes without changing unrelated command behavior.
- **Config writes are explicit local effects.** `local_config_change` is metadata-visible but does not require remote mutation authorization.
- **Safety preference needs acknowledgement.** Disabling destructive confirmation is allowed only through an explicit flag and never authorizes mutations.

## Acceptance Criteria

- [ ] `config list` lists every supported non-secret setting and its effective value/source in human-readable and JSON forms.
- [ ] `config get KEY` returns a stable object containing public key, effective value, source layer, and source detail such as the exact environment variable when applicable.
- [ ] `config set KEY VALUE` and `config unset KEY` modify only supported persisted overrides using registry validation.
- [ ] The registry explicitly maps public/TOML/internal names, including `timeout` to `timeout_seconds`, and identifies all relevant environment sources such as `NO_COLOR` and `MONARCH_NO_COLOR`.
- [ ] Mutation authorization, credentials, session contents, cookie/token values, and non-interactive authorization are absent from list/get/set/unset and cannot be persisted through generic keys.
- [ ] Disabling `confirm_destructive` requires an explicit acknowledgement option; it does not authorize a remote mutation or persist mutation authorization.
- [ ] Unknown keys, invalid values, malformed booleans/numbers/enums, and non-writable locations fail with stable actionable errors and no partial write.
- [ ] Malformed existing TOML is diagnosed by config management commands and is never silently overwritten, repaired, or truncated by set/unset.
- [ ] Environment, CLI, and default values are never accidentally persisted; after set, the persisted layer changes only for the requested key, while a higher active override remains effective and visible.
- [ ] Unset removes only the requested file override, preserves unrelated settings, and reveals the next source according to documented precedence.
- [ ] `tomlkit>=0.13,<1` is declared directly; writes preserve unrelated valid settings, comments, and formatting and pass clean-install/lock verification.
- [ ] Writes use same-directory temporary files and atomic replacement, preserve appropriate existing file permissions where possible, and never loosen shared config-directory or credential-file permissions.
- [ ] Concurrent writes are documented as last-writer-wins; atomicity prevents torn files but does not claim multi-process transactional merging.
- [ ] Mutating config commands declare `local_config_change`; read commands declare `read_only`; shared metadata/capability tests enforce the classification.
- [ ] Config commands never prompt, have deterministic non-interactive exit codes, and emit machine-readable errors on the documented stream without prose or ANSI escapes.
- [ ] Unit/CLI tests cover defaults, file/env/CLI precedence, exact provenance, NO_COLOR precedence, set/unset, safety acknowledgement, corrupt input, unknown fields preservation, comments preservation, write failures, atomic replacement, and output contracts.
- [ ] User-facing documentation and repository verification pass.
