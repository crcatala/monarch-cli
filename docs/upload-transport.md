# Credential-safe upload transport

Transaction attachment upload sends file bytes to a third-party media host that
must never receive Monarch credentials, cookies, CSRF values, or session state.
This document records the trust boundary and its maintenance assumptions
(ticket `mc-sr92`).

## The problem

The released `monarchmoneycommunity` client (1.5.2, the newest release at the
time of writing) has no public, credential-isolated attachment upload.
`MonarchMoney.upload_attachment()` performs the third-party media upload through
its private `_upload_form_data()` helper, which copies the authenticated
client's outbound headers and removes only `Accept` / `Content-Type` (and, for
non-Monarch hosts, the cookie and CSRF headers). In token-authentication mode
that leaves the Monarch `Authorization: Token ...` header attached to the
request sent to the media host, leaking Monarch credentials off-origin.

Because this CLI authenticates with a token, that path must not be used until a
safe transport exists. No released upstream version provides one, so the CLI
owns a narrow local adapter instead.

## The boundary

`monarch_cli.core.upload_transport` is the only module that talks to the
third-party media host. It:

- builds third-party request headers from an explicit destination allowlist
  (`User-Agent` only) and signed form fields from an explicit signed-field
  allowlist (`timestamp`, `folder`, `signature`, `api_key`, `upload_preset`);
  it never copies and prunes the authenticated client's headers;
- pins the destination to `https://api.cloudinary.com/v1_1/monarch-money/image/upload/`
  and ignores the server-supplied upload `path`, so remote data cannot steer the
  destination;
- disables redirects (`allow_redirects=False`) and treats a 3xx as a definitive
  failure, so request headers can never be forwarded to another origin;
- keeps each stage distinct: `acquire_upload_params` (authenticated Monarch
  signed parameters), `upload_media` (credential-safe third-party transport),
  and `register_attachment` (authenticated Monarch registration);
- treats signed parameters, destination details, and media-host responses as
  sensitive: they are never logged, emitted in structured output, or copied into
  diagnostics, and the relevant dataclasses have redacted `repr`s.

Commands and services consume only this adapter boundary. They never call the
upstream client's private stage methods or `MonarchMoney.upload_attachment()`.

The consuming attachment workflow is `transactions attachments add` (mc-2v9a).
It owns file policy, exact target verification, and the staged mutation outcome;
it calls `acquire_upload_params`, `upload_media`, and `register_attachment`
individually and never treats the three stages as an atomic operation.

## Outcome classification

The media stage performs exactly **one** attempt and never retries (a retry
after the request may have been dispatched could create a second orphaned
asset). It classifies honestly for the `mutation-outcome.v1` contract:

| Media-host result | Classification |
|---|---|
| 2xx with usable media identity | success (`MediaUploadResult`) |
| refused redirect (3xx) or client rejection (4xx) | definitive failure (`MediaUploadError`) |
| server error (5xx), unusable success body, timeout, or transport failure | ambiguous (`MutationAmbiguousError`) |

Interpreting these stages into a full mutation outcome, file policy, retry
policy, and transaction verification belongs to the consuming attachment
workflow (`mc-2v9a`) and the shared P0 mutation contracts, not to this
transport boundary.

## Maintenance assumptions

The authenticated stages call the released client's private
`_get_transaction_attachment_upload_info` and `_add_transaction_attachment`
methods, because `monarchmoneycommunity` 1.5.2 exposes no public per-stage
interface. The compatibility contract tests in `tests/core/test_client_interface.py`
assert those methods exist and remain awaitable; the credential-isolation tests
in `tests/core/test_upload_transport.py` inspect prepared and captured outbound
requests for token- and cookie-authenticated client states and fail if any
credential material is present.

If a future `monarchmoneycommunity` release exposes a public, credential-safe,
stage-aware upload interface, replace the adapter with a thin delegation, delete
the private-method bridge, and keep the credential-isolation tests passing. A
dependency version bump alone is not evidence of safety.
