---
id: mc-oqc9
status: open
deps: [mc-h3cl]
links: [mc-7wqj]
created: 2026-09-11T12:20:08Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, institutions, subscription, read-only, diagnostics]
---
# Expose institution and subscription status

Expose connected institutions and subscription state through stable, non-misleading read-only contracts useful for connection diagnostics and entitlement discovery.

## Design

Add a first-class `institutions` read surface centered on credentials/connections, because the released upstream response attaches status primarily to credentials rather than directly to accounts. Normalize credential identity, provider, institution identity/name, update-required/disconnected state, last update, reported issues, balance/transaction status, and associated accounts.

The upstream institutions response includes deleted accounts and a small subscription fragment. Exclude deleted accounts by default, expose an explicit include-deleted option, and always retain deletion state when included. Subscription fields have one authoritative normalized home under `subscription show`; the institutions transformer must not create a competing subscription contract from its embedded fragment.

`subscription show` exposes the stable entitlement/trial state available from `get_subscription_details`. Treat unavailable subscription data distinctly from a known free or non-premium state. Do not expose referral codes or payment-source details by default unless separately justified as safe and useful; raw mode may preserve the upstream response explicitly.

Credit history is outside this ticket and is tracked by `mc-kzp9`.

## Key Decisions

- **Institution status is credential-centric.** This matches the actual connection/status model returned upstream.
- **Deleted accounts are opt-in.** Diagnostic completeness must not make deleted records look active.
- **Subscription has one authoritative contract.** Embedded institution-response fields do not define a second schema.
- **Minimize sensitive/default output.** Referral and payment-source metadata are not part of the normalized default.

## Acceptance Criteria

- [ ] A discoverable institutions command returns normalized credential/connection and institution status with associated active accounts.
- [ ] Credential identity, provider, institution identity/name, update-required, disconnected, last-updated, issue, balance-status, and transaction-status fields have documented null/unavailable semantics.
- [ ] Deleted accounts are excluded by default; an explicit option includes them with deletion state clearly represented.
- [ ] Null institutions, credentials without institutions, partial status fields, empty credentials, and unavailable account lists do not crash or produce misleading healthy-state defaults.
- [ ] `subscription show` returns documented normalized trial and premium-entitlement state and distinguishes unavailable data from known false values.
- [ ] Referral code and payment-source values are excluded from normalized default output; explicit raw mode preserves the upstream response without transformation.
- [ ] Subscription values embedded in the institutions response are not published as a second normalized subscription contract.
- [ ] Both commands are classified read-only and perform no remote mutation.
- [ ] JSON and human-readable output remain stable and useful without exposing credentials, session data, or unnecessary sensitive metadata.
- [ ] Unit/CLI tests verify API mapping, credential-centric grouping, deleted-account behavior, null/partial/empty responses, unavailable subscription state, output formats, and negative paths.
- [ ] The required upstream-client compatibility floor is verified, user-facing privacy/command documentation is complete, and repository verification passes.
