---
id: mc-ic7w
status: closed
deps: []
links: []
created: 2026-09-19T17:37:24Z
type: bug
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [safety, mutation, regression]
---
# Classify gql transport failures as ambiguous mutation outcomes

A remote mutation whose transport fails after the request was dispatched is reported as a definitive failure rather than ambiguous, even though the write may have succeeded remotely. This breaks the mutation-outcome contract and can cause a caller to retry a write that already applied.

## Root cause
The upstream `monarchmoney` client performs every API call through `MonarchMoney.gql_call`, which uses the `gql` library. gql's aiohttp transport wraps *all* transport failures as `gql.transport.exceptions.TransportConnectionFailed` (see `.venv/.../gql/transport/aiohttp.py`: `except TransportError: raise` / `except Exception as e: raise TransportConnectionFailed(str(e)) from e`).

`TransportConnectionFailed` derives from `TransportError` -> `Exception`; it is NOT a `ConnectionError`, `OSError`, or aiohttp exception. It is therefore absent from `RETRYABLE_EXCEPTIONS` and `AMBIGUOUS_TRANSPORT_EXCEPTIONS` in `src/monarch_cli/core/retry.py`, so `run_mutation_call` does not convert it to `MutationAmbiguousError`. It falls through to the generic `except Exception` handler and is reported as `status: failed`, `code: UNKNOWN`, exit 1, with `verification: null`.

Because every mutation goes through `gql_call`, this affects all mutation commands (transactions update/create/delete/batch-update, tags, splits, attachments, review mark/return, budgets set, accounts refresh).

## Reproduction (observed live)
Same post-dispatch disconnect fault injected at two layers, against a disposable fixture:

| Fault layer | Write applied remotely | Exit | Status | Details |
|---|---|---|---|---|
| Through gql (`review return`) | yes (needs_review=true) | 1 | failed | code=UNKNOWN, exception_class=TransportConnectionFailed, no verification |
| Through gql (`budgets set`) | yes (budgeted=value) | 1 | failed | code=UNKNOWN, no verification |
| Raw aiohttp error above gql (control) | yes | 4 | ambiguous | reason=transport_failure, verification present |

The control proves the classification logic is correct but never receives the real exception type.

## Why existing tests miss it
Per-command "transport ambiguity (no retry)" tests inject the inner exception type (aiohttp/OSError/TimeoutError) directly at the client-call boundary, bypassing the gql wrapping that happens in production. They therefore pass while real transport failures are misclassified.

## Design

Add the gql transport exception hierarchy to the CLI's ambiguity classification so a dispatched-but-unconfirmed write is never reported as a definitive failure.

Preferred approach: import `gql.transport.exceptions.TransportError` (or at least `TransportConnectionFailed`) and include it in the ambiguous/retryable sets used by `run_mutation_call`. `gql` is already a direct, bounded dependency (`gql>=4.0,<5`).

Consider a defensive design so an unknown third-party wrapper cannot silently downgrade ambiguity again: classify ambiguity by operation stage (request dispatched vs not) rather than by an exhaustive exception-type allowlist, or add a catch-all for non-CLI exceptions raised after dispatch.

Keep this distinct from read-path retry behavior: reads may retry; mutations must never retry automatically and must report ambiguity when the outcome is unknown.

## Acceptance criteria
- A transport failure raised through the real gql transport layer during a mutation is reported as `status: ambiguous` with `remote_state: unknown`, exit code 4, and a verification hint.
- The failure is never reported as `status: failed` with `code: UNKNOWN` when the request was already dispatched.
- No automatic retry occurs for mutations.
- A regression test raises the failure through the actual gql transport (not merely the inner aiohttp type), so the gql wrapping is exercised.
- A test proves a definitive service rejection (e.g. GraphQL `errors` payload) still reports `failed`, not `ambiguous`.
- Existing mutation outcome and exit-code contracts and documentation remain accurate (update `docs/mutation-outcomes.md` if needed).


## Notes

**2026-09-19T17:51:52Z**

Live reproduction — 2026-09-19, disposable test account (mc-cr09 verification pass).

Two-layer control on disposable fixtures (write actually applied in every case):

| Fault layer | Write applied remotely | Exit | Status | Details |
|---|---|---|---|---|
| Through gql (`transactions review return`) | yes (needs_review=true) | 1 | failed | code=UNKNOWN, exception_class=TransportConnectionFailed, verification=null |
| Through gql (`budgets set`) | yes (budgeted=value) | 1 | failed | code=UNKNOWN, verification=null |
| Raw aiohttp error above gql (control) | yes | 4 | ambiguous | reason=transport_failure, verification present |

The control — dispatching the real write and then raising `aiohttp.ServerDisconnectedError` *above* `MonarchMoney.gql_call` — proves the CLI classification logic is correct; the production path never sees that type because gql wraps everything as `TransportConnectionFailed`.

Repro technique: patch `aiohttp.ClientSession._request` (through gql) or `MonarchMoney.gql_call` (above gql) to dispatch the request and then raise. Confirm the remote effect by reading state back after the CLI reports `failed`.

Also observed: the read path retries (4 attempts then NETWORK_ERROR), while the mutation path is single-attempt. Any fix must preserve non-retry semantics for mutations.

**2026-09-19T18:00:50Z**

Fix implemented on branch fix/mc-ic7w-gql-transport-ambiguity and opened as PR https://github.com/crcatala/monarch-cli/pull/89.

Classification changes:
- gql.transport.exceptions.TransportConnectionFailed added to RETRYABLE_EXCEPTIONS (src/monarch_cli/core/retry.py), which also makes it ambiguous on the mutation path since AMBIGUOUS_TRANSPORT_EXCEPTIONS is derived from that set.
- Defensive catch-all for the gql TransportError base class in run_mutation_api_call_async treats any in-flight transport failure as ambiguous, so a future gql exception cannot silently downgrade a dispatched write.
- Definitive rejections stay definitive: TransportQueryError (GraphQL errors), TransportAlreadyConnected/Closed, and 4xx TransportServerError; 5xx is ambiguous.

Tests: real gql transport wrapping exercised by patching aiohttp.ClientSession.post (gql raises TransportConnectionFailed), plus raw wrapper, GraphQL errors, 4xx/5xx, read retry, and a command-level budgets set envelope test (exit 4, remote_state unknown, verification present). Docs + changelog updated.

**2026-09-19T18:25:15Z**

Re-verification after fix (PR #89, commit 0955d55) — 2026-09-19, disposable test account.

Re-ran the live through-gql fault injection on disposable fixtures. Every case now matches the contract.

| Case | Injection | Before fix | After fix |
|---|---|---|---|
| A | `transactions review return` + disconnect through gql | exit 1, failed, UNKNOWN | exit 4, ambiguous, reason=transport_failure, remote_state=unknown, verification present |
| B | `budgets set` + disconnect through gql | exit 1, failed, UNKNOWN | exit 4, ambiguous, MUTATION_AMBIGUOUS, verification present |
| C | definitive GraphQL rejection (`TransportQueryError`) | — | exit 1, failed (correctly NOT ambiguous) |
| D | `TransportServerError` code 500 | — | exit 4, ambiguous |
| E | `TransportServerError` code 400 | — | exit 1, failed (definitive) |

Additional confirmations:
- Single-attempt mutations preserved: exactly one write dispatch in A and B, no automatic retry.
- Writes actually applied in A and B (needs_review=true / budgeted=value), so `ambiguous` is the correct verdict.
- Read path still retries: injecting `TransportConnectionFailed` on `accounts list` produced 4 transport attempts then a structured `NETWORK_ERROR`, confirming the new retryable entry does not break read behavior or leak into mutation retry.

All fixtures deleted; final state restored (original 3 transactions, budgets at budgeted=0). Verification complete — closing.
