---
id: mc-61tf
status: in_progress
deps: []
links: []
created: 2026-09-19T17:51:42Z
type: task
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [contract, schema, read-only]
---
# Expose review metadata in normalized transaction detail

Observed during the mc-cr09 live verification pass (disposable test account).

`monarch transactions get <id> --strict` returns `needs_review` and `review_status` in the normalized detail, but:
- it does NOT expose `reviewed_at` or `reviewed_by_user`, even though the review commands report both from their own detail read (`transactions review mark`/`return` write responses and results include them); and
- `review_status` is always `null` in the observed output.

Consequence: a consumer relying on the normalized detail cannot observe when/by whom a transaction was reviewed, and cannot tell whether `review_status` is meaningful or a placeholder.

Example (real fixture): the review write reported `reviewed_at=2026-09-19T17:29:12Z` and `reviewed_by_user={id,name}`, while `transactions get --strict` showed `needs_review=false`, `review_status=null`, and no review timestamps.

This is not a functional defect in the review commands; it is a normalized-contract gap.

## Design

Decide the intended contract and make it explicit:

Option A (preferred if the data is available): add optional `reviewed_at` and `reviewed_by_user` to the normalized transaction-detail contract. Under docs/schema-contracts.md this is an additive change (new optional property) and needs no schema version bump. Update `src/monarch_cli/schemas/transaction-detail.v1.json`, the normalizer, and `docs/commands.md`.

Option B: document deliberately that review timestamps are only available through the review command output, with rationale, and remove or clarify `review_status`.

Either way, resolve why `review_status` is always null (unimplemented placeholder vs intentional).

Do not change the review-mutation wire input; this is about read/normalized output only.

## Acceptance Criteria

Either `reviewed_at`/`reviewed_by_user` are exposed in normalized detail (additive, schema + normalizer + docs updated, tests added), or their omission is explicitly documented with rationale.
`review_status` is either populated meaningfully or clearly documented/deprecated.
The published `transaction-detail:v1` schema and `docs/schema-contracts.md` compatibility table remain accurate.
A test pins the chosen behavior against a fixture detail payload.


## Notes

**2026-09-19T18:45:07Z**

Implementation opened as PR https://github.com/crcatala/monarch-cli/pull/90 (branch feat/mc-61tf-review-metadata).

Chose Option A, detail-only. `transform_transaction_detail` now emits `reviewed_at` (literal reviewedAt) and `reviewed_by_user` (normalized reviewedByUser as {id, name}, mirroring the review-command output shape). Both nullable, always emitted. Added as optional additive properties on transaction-detail:v1 (not required) so no version bump per docs/schema-contracts.md. transaction.v1 (list) and the shared transform_transaction are unchanged: list-endpoint population of review attribution is not established, so no speculative always-null fields.

review_status retained (removal would be breaking) and documented in the schema/docs as a placeholder the public detail endpoint has not been observed to populate; needs_review remains the queue-state field.

Tests: normalization, malformed reviewedByUser tolerance (null/string/list/empty-object), the detail-only boundary (list output must not grow fields), plus schema conformance and exact key-set equality against a detail fixture. Verified: ruff format/lint clean, mypy clean, `uv run pytest -m "not live"` -> 1448 passed, 21 deselected. No schema version bump.
