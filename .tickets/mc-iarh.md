---
id: mc-iarh
status: open
deps: [mc-8dfd]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [p3, household, ownership, read-only, discovery]
---
# Add read-only household member discovery

Let shared households resolve ownership identifiers to current household members before filtering, interpreting, or changing owned records. The directory resolves real member IDs to display values and roles; it does not infer why an account or transaction has null ownership.

## Design

Add `monarch household members list` as a small read-only household-domain command backed by adapter, service, and transformer boundaries. Require the first stable `monarchmoneycommunity` release containing the dedicated `get_household_members()` method and declare that exact minimum version in project metadata and client-interface tests. Do not use `get_credit_history()` as a transport because it fetches unrelated credit-score, profile, and third-party onboarding data; do not depend on an unreleased branch or add command-local raw GraphQL as a fallback.

The normalized member contract is exactly:

- `id`: non-empty opaque household-member identifier;
- `display_name`: nullable display value, using non-empty upstream `displayName`, then non-empty `name`, then null;
- `role`: nullable upstream household role preserved without inventing permissions or mapping unknown values to known roles.

Exclude raw name duplication, profile-picture URLs, email/authentication data, invitation metadata, credit/Spinwheel identifiers or statuses, onboarding/error details, optional household-profile context, and all other upstream fields. This command intentionally offers no raw mode because raw passthrough would bypass the privacy allowlist. Human output shows only the display name, role when present, and member ID needed for automation.

Preserve the household-member order returned by the dedicated upstream method; do not invent a local role hierarchy. Repeated serialization of the same response is deterministic. Pending invitations are not members and are excluded by the upstream method rather than returned with a pending status. Missing/null fields must not be labeled pending, invited, shared, or unassigned.

Keep member discovery separate from ownership mutation so it can land and be reviewed independently. Consistent with mc-8dfd, null account/transaction ownership remains semantically unknown: the member directory helps resolve non-null owner IDs but cannot distinguish Shared, unassigned, unavailable, or unsupported ownership states.

## Key Decisions

- **Dedicated minimal upstream query.** Never fetch credit history to obtain a member directory.
- **Privacy allowlist, not denylist.** Normalized output contains only ID, display name, and role.
- **No raw mode.** Raw household payloads could bypass the field allowlist.
- **No invented ownership state.** The command resolves members but does not classify null ownership.
- **Pending invitations are absent.** They are not represented as synthetic members or statuses.
- **Preserve upstream household order.** Do not invent role precedence.

## Acceptance Criteria

- [ ] `monarch household members list` is a discoverable read-only command and performs no remote mutation.
- [ ] Every normalized entry contains exactly `id`, nullable `display_name`, and nullable `role`; display fallback is non-empty `displayName`, then non-empty `name`, then null.
- [ ] Member IDs are non-empty opaque strings; malformed or missing IDs do not produce synthetic identities and follow documented skip-or-typed-error behavior.
- [ ] Unknown role values are preserved as unknown upstream values and are not mapped to fabricated permissions or known roles.
- [ ] Pending invitations are not returned as members; missing/null data is never labeled pending, invited, Shared, unassigned, or unavailable without upstream evidence.
- [ ] Documentation reiterates mc-8dfd's contract that null account/transaction ownership cannot be resolved into Shared versus unassigned state by this directory.
- [ ] Every renderer and error path consumes only the normalized `{id, display_name, role}` allowlisted model; raw mode is unavailable, and negative sentinel tests prove extra upstream fields cannot leak through any supported output or diagnostic path.
- [ ] JSON and human-readable formats preserve upstream member order and serialize the same normalized response deterministically; quiet output remains ID-only.
- [ ] Adapter/service/transformer boundaries isolate the upstream shape, and the implementation never calls `get_credit_history()` or performs extra profile/onboarding requests.
- [ ] Tests cover complete, single-member, empty, missing/null users, null/partial members, missing/duplicate/invalid IDs, unknown/null roles, non-object entries, malformed roots, format behavior, privacy exclusions, authentication errors, API errors, and command discovery.
- [ ] The exact stable upstream version containing `get_household_members()` is declared in project metadata, lock data, and client-interface tests; no development-branch or command-local raw-GraphQL fallback is used.
- [ ] User-facing documentation explains the command, display fallback, role limitations, pending-invitation exclusion, ownership-null ambiguity, and privacy policy; repository verification passes.
