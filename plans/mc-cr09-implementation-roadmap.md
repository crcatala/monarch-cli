# mc-cr09 implementation roadmap

_Reviewed against the ticket set on 2026-09-11._

## Epic intent

`mc-cr09` expands Monarch CLI into a safer automation surface for humans and agents. The roadmap first establishes install, authentication, mutation, retry, outcome, and non-interactive guarantees; then adds read-only discovery and carefully guarded mutations; and finally publishes schemas, capability discovery, configuration UX, and separately gated live verification.

The governing rule is: **land shared safety and contract primitives before adding new writes, and never make live financial state the default test fixture.**

## Ticket scope and purpose

### P0 — safety and release foundations

| Ticket | Scope | Why / what it enables |
|---|---|---|
| `mc-43s0` | Correct runtime dependency metadata, constrain Typer, regenerate the lock, test Python 3.12/3.13, and add an isolated wheel-install smoke target used by CI/releases. | Establishes a reproducible consumer install before broad CLI changes. Directly unblocks `mc-h3cl`, `mc-sr92`, `mc-9b8s`, `mc-wtfb`, and `mc-82kf`. |
| `mc-2nj4` | Remove every pickle session path and `file-compat` option; detect legacy files only by metadata and require safe re-authentication. | Eliminates a local code-execution boundary while preserving token/keyring/atomic-JSON precedence. Directly unblocks cookie authentication (`mc-9b8s`). |
| `mc-k48z` | Add explicit operation-effect metadata, a read-only default, per-invocation `--allow-mutations`, and enforcement at both command registration and remote execution. | Creates the trust boundary inherited by all current and future remote mutations. Directly unblocks `mc-t9o7`, `mc-2btg`, every mutation feature, config/capability metadata, and live mutation testing. |
| `mc-2btg` | Centralize prompt policy and add deterministic non-interactive behavior for flags, environment/config, errors, streams, and exit codes. | Prevents CI and agents from hanging and keeps non-interactivity separate from mutation authorization/confirmation. Enables unattended mutation, auth, config, capabilities, and live-test workflows. |
| `mc-t9o7` | Separate read and mutation executors; disable automatic retries for current mutations; classify potentially dispatched transport failures as ambiguous with recovery guidance. | Prevents duplicate writes and false “failed” claims. Directly unblocks the shared mutation outcome contract and safe live mutation testing. |
| `mc-ik8o` | Adopt `mutation-outcome.v1` for account refresh and transaction single/batch writes, including success, failure, ambiguity, partial completion, verification, and exit semantics. | Gives automation one outcome model for atomic, batch, and multi-stage writes. Enables all later mutation features and schema/capability publication. |

### P1 — normalized reads and first guarded workflows

| Ticket | Scope | Why / what it enables |
|---|---|---|
| `mc-h3cl` | Harden account, transaction, and cashflow transformers against null/missing/evolving upstream shapes; correct pending-state mapping; preserve stable normalized keys and raw passthrough. | Establishes the reliable API normalization boundary used by nearly every new read command and by published schemas. |
| `mc-hszv` | Add transaction detail and the released list-filter surface, including tri-state filters, strict pending redirects, validation, and separate pending/review semantics. | Lets callers find and inspect exact records before acting. Directly enables tags, splits, attachments, review mutations, and ownership output. |
| `mc-7xfl` | Add normalized, deterministic account group/type/subtype discovery. | Replaces guessed account identifiers with authoritative values. Directly enables account snapshot/history filter validation and liability metadata. |
| `mc-4edf` | Add account history, recent balances, aggregate/type snapshots, and observational refresh status with method-specific date rules and unknown-ID handling. | Enables net-worth/sync visibility and safe before/after verification without initiating refreshes. |
| `mc-7wqj` | Add normalized category, category-group, merchant, and overall `cashflow detail` using shared date and summary semantics. | Expands read-only reporting without fictional pagination or duplicate summary calls. |
| `mc-nbvi` | Add all-time transaction summary and date-scoped recurring activity reads. | Enables aggregate and recurring-activity automation while keeping API semantics explicit. |
| `mc-oqc9` | Add credential-centric institution status and privacy-minimized subscription state, with deleted accounts opt-in. | Enables connection diagnosis and entitlement discovery without leaking session/payment/referral data. |
| `mc-ppai` | Add normalized multi-account holdings via bounded per-account fanout, source-account annotation, conservative aggregation, and no cross-account monetary totals. | Enables portfolio inventory/allocation reads despite the released client lacking a bulk endpoint. |
| `mc-sr92` | Establish an allowlisted third-party upload adapter that cannot forward Monarch tokens, cookies, CSRF, or session headers. | Removes a credential-exfiltration risk and directly enables transaction attachment upload. |
| `mc-87ez` | Add tag list/show/create and explicit full-set replace/clear for one transaction, with validation, confirmation, verification, and shared outcomes. | Enables safe classification workflows without pretending unsupported incremental updates are atomic. |
| `mc-hp7w` | Add split show/replace/clear with bounded JSON input, exact Decimal total validation, server error handling, and post-write verification. | Enables deliberate allocation changes while preventing malformed totals and unsafe retries. |
| `mc-2v9a` | Add offline attachment dry-run plus a three-stage signed-parameter/upload/register workflow using one validated file descriptor and the safe upload adapter. | Enables transaction document attachment with honest orphan/partial/ambiguous outcomes. Directly enables receipt-inbox work through shared file primitives. |

### P2 — richer semantics and authentication

| Ticket | Scope | Why / what it enables |
|---|---|---|
| `mc-8dfd` | Add nullable owner identity to normalized account and transaction outputs and expose ownership override timestamps without inferring “shared.” | Enables ownership-aware filtering/explanation and directly unlocks household-member discovery. |
| `mc-r75q` | Add direct asset/liability classification and distinct nullable limits, rates, payment, and debt-paydown fields to account output. | Enables debt/account analysis without invented units, payoff math, or merged upstream concepts. |
| `mc-e49c` | Add explicit “mark reviewed” and “return to review queue” mutations with exact one-field payloads and pre/post verification. | Enables transaction triage while avoiding ambiguous booleans and accidental category/merchant nulling. |
| `mc-frmf` | Add offline preview and a three-stage receipt-inbox create/upload/start workflow, reporting only initial status and requiring manual recovery for ambiguity. | Enables capture-first receipt automation when no transaction is known, without claiming downstream matching completed. |
| `mc-9b8s` | Add typed, versioned token-or-cookie sessions and secret-safe cookie import from protected file/stdin, with deterministic precedence, storage, diagnostics, and logout. | Enables CAPTCHA/browser-session users and automation while keeping secrets out of argv/output and never reviving pickle persistence. |

### P3 — automation UX, privacy-gated features, and live evidence

| Ticket | Scope | Why / what it enables |
|---|---|---|
| `mc-wtfb` | Add registry-driven `config list/get/set/unset`, provenance, TOML-preserving atomic writes, and a `local_config_change` effect; exclude secrets and mutation authorization. | Enables supported configuration automation and supplies authoritative config metadata for capability discovery. |
| `mc-iarh` | Add privacy-allowlisted household member discovery returning only ID, display name, and role; no raw mode. | Resolves owner IDs without fetching credit/profile data. Directly enables guarded ownership updates. |
| `mc-bf8f` | Add a dedicated member-or-Shared ownership mutation with local dry-run, member validation, bounded readback, and ambiguity when Shared cannot be affirmatively proven. | Enables ownership changes without exposing upstream magic values or pretending null ownership proves Shared. |
| `mc-eruy` | Add read-only rule inspection from a future stable upstream method, preserving upstream order and explicit unsupported shapes without simulating the rule engine. | Enables diagnosis/audit of automatic transaction behavior. |
| `mc-kzp9` | Research-only credit-history decision with privacy-minimized structural evidence and an explicit go/no-go document; no public command. | Prevents prematurely publishing a sensitive, unstable contract. A “go” creates a new implementation ticket depending on `mc-h3cl`. |
| `mc-cpzi` | Package Draft 2020-12 schemas for normalized account/transaction output, structured errors, and `mutation-outcome.v1`, with stable URNs and one code mapping. | Enables downstream validation and directly unlocks the live schema smoke suite and capabilities manifest. |
| `mc-vcbk` | Convert the local live suite into a bounded, opt-in, read-only installed-CLI contract/schema smoke matrix; remove mutation tests from the ordinary live gate. | Detects real API drift safely before releases and finishes the linked `mc-3437` infrastructure. |
| `mc-584r` | Add a separately selected and authorized live-mutation suite using a verified test household, disposable account/transaction fixtures, recovery journal, and ambiguity-safe cleanup. | Provides controlled end-to-end evidence for mutation foundations without touching ordinary household records. Initial scope proves only notes update. |
| `mc-82kf` | Emit a deterministic, side-effect-free JSON manifest of every command, syntax, effects, prompting, output support, and schema references. | Enables agents/integrations to discover the installed CLI instead of scraping help or guessing safety behavior. Best landed after the command surface stabilizes. |

### Linked prerequisite outside this epic

| Ticket | Scope | Why / what it enables |
|---|---|---|
| `mc-3437` | Existing local-only live test runner, markers, Make target, throttling, and docs. Its current partial implementation includes mutation tests against an arbitrary existing transaction. | Direct dependency of both live suites. It should be hardened early: remove/disable ordinary-household mutation tests and leave a safe read-only runner for `mc-vcbk` and isolated infrastructure for `mc-584r`. |

`mc-cd12` (schema contract tests) and `mc-c165` (transformer tests) are already closed prerequisites/supporting work.

## Recommended sequential PR order

This is a dependency-valid, risk-first order for one agent producing one reviewed PR at a time. The one deliberate priority exception is bringing `mc-584r` forward after P0 so a human can prove the mutation foundation on disposable records before more write features accumulate.

0. **`mc-3437` (linked prerequisite/hygiene):** remove or disable the currently broad live mutation cases, retain a bounded read-only local runner, and make CI exclusion explicit.
1. **`mc-43s0`:** establish reproducible installs and framework compatibility first.
2. **`mc-2nj4`:** remove the highest-impact legacy credential hazard.
3. **`mc-k48z`:** land the operation taxonomy and read-only mutation gate.
4. **`mc-2btg`:** make every prompt path deterministic for unattended execution.
5. **`mc-t9o7`:** split read/write execution and establish ambiguity semantics.
6. **`mc-ik8o`:** normalize all existing mutation results.
7. **`mc-584r`:** implement the isolated disposable-fixture mutation harness, then require human live proof before relying on it.
8. **`mc-h3cl`:** harden the normalization boundary.
9. **`mc-hszv`:** build transaction discovery/detail needed by later writes.
10. **`mc-7xfl`:** add account type discovery.
11. **`mc-sr92`:** independently security-review upload transport before any upload command.
12. **`mc-4edf`:** add account history/snapshot/refresh reads.
13. **`mc-7wqj`:** add cashflow detail.
14. **`mc-nbvi`:** add transaction summary/recurring reads.
15. **`mc-oqc9`:** add institution/subscription status.
16. **`mc-ppai`:** add bounded holdings fanout and normalization.
17. **`mc-87ez`:** add tag workflows on the complete shared mutation stack.
18. **`mc-hp7w`:** add split workflows as a separate high-risk mutation review.
19. **`mc-2v9a`:** add transaction attachments after transport and file-policy prerequisites.
20. **`mc-8dfd`:** expose ownership in established account/transaction contracts.
21. **`mc-r75q`:** finalize additive account liability fields before publishing account schemas.
22. **`mc-e49c`:** add review-state mutation after an explicit upstream payload-shape decision.
23. **`mc-frmf`:** add receipt inbox by reusing the reviewed file primitives.
24. **`mc-9b8s`:** add cookie sessions after pickle removal and prompt policy are stable.
25. **`mc-wtfb`:** add safe config management and its new local-effect metadata.
26. **`mc-iarh`:** add the minimal member directory once a qualifying stable upstream release exists.
27. **`mc-bf8f`:** add ownership mutation only after the member directory and proving-signal review.
28. **`mc-eruy`:** add rule inspection once its required stable upstream method is released.
29. **`mc-kzp9`:** make and review the credit-history go/no-go decision; insert any resulting implementation ticket here, before final discovery publication.
30. **`mc-cpzi`:** publish schemas after account/transaction fields and mutation semantics have settled, minimizing schema churn.
31. **`mc-vcbk`:** validate the final read-only contract set against the live service using the hardened `mc-3437` runner.
32. **`mc-82kf`:** publish capabilities last so its canonical manifest fixture reflects the full installed command surface.

### External readiness gates

Do not start these implementation PRs merely because they are next in the list:

- **`mc-sr92`:** first check for a compatible released upstream credential-isolation fix; otherwise explicitly approve ownership of the local public adapter.
- **`mc-e49c`:** choose and document one of the ticket's ordered payload-safety options before coding; do not accept unrelated nullable fields casually.
- **`mc-iarh` / `mc-bf8f`:** require a stable release with the dedicated member method, and for ownership, stable `owner_user_id` support plus an honest Shared verification decision.
- **`mc-eruy`:** wait for a stable release containing `get_transaction_rules()`; no unreleased branch/raw GraphQL fallback.
- **`mc-kzp9`:** a human owns the privacy/product go/no-go decision and any opt-in live research approval.

If an upstream gate is closed, skip that ticket temporarily and continue with the next dependency-ready ticket; return to it before `mc-cpzi`/`mc-82kf` if it changes a published stable output surface.

## PR grouping recommendation

**Default: one ticket per PR.** The epic and individual ticket designs intentionally separate trust boundaries, runtime contracts, domain behavior, and publication. Separate PRs give clean rollback points and make security review tractable.

Strongly keep these in their own PRs:

- Every P0 ticket.
- `mc-h3cl` (broad transformer contract impact).
- `mc-sr92`, `mc-2v9a`, `mc-frmf` (credential/file/upload boundaries).
- Every mutation feature: `mc-87ez`, `mc-hp7w`, `mc-e49c`, `mc-bf8f`.
- `mc-9b8s` (credential model and secret handling).
- `mc-584r` and `mc-vcbk` (different live gates and risk classes).
- `mc-kzp9` (independently approved research decision).
- `mc-cpzi` and `mc-82kf` (schema correctness should land before manifest consumption).

One **optional** combination is `mc-8dfd` + `mc-r75q` because both are additive normalized account-output changes and touch common transformer/render/schema fixtures. Only combine them if the resulting diff remains reviewable; ownership privacy semantics and liability units still need separate test sections and commits. The recommended order assumes separate PRs.

Avoid tempting combinations even where code overlaps:

- `mc-k48z` + `mc-t9o7` + `mc-ik8o`: authorization, execution, and output are separate failure domains.
- `mc-sr92` + `mc-2v9a`: review credential isolation before introducing its first consumer.
- `mc-h3cl` + read features: prove the boundary before expanding it.
- `mc-7xfl` + `mc-4edf`: the latter already contains five commands and should consume a landed discovery contract.
- `mc-iarh` + `mc-bf8f`: land and privacy-review read-only discovery before ownership writes.
- `mc-3437` + `mc-vcbk`: remediate the existing unsafe live-test shape early; schema-backed smoke expansion lands later.

## Human verification checkpoints

Agents should implement mocked/contract tests, but a trusted human should hold credentials, choose the household, invoke live gates, and inspect cleanup in the Monarch UI.

### Checkpoint A — after P0 (`mc-ik8o`)

Safe local/manual checks:

- Install the built wheel in clean Python 3.12 and 3.13 environments and invoke both entry points.
- Exercise representative reads, auth status/logout, dry-runs, JSON errors, and non-interactive failures.
- Confirm every current mutation is blocked without `--allow-mutations`, blocked before authentication/prompting, and authorized only for one invocation.
- Review exit `3` for blocked mutation and exit `4` for ambiguity/partial outcomes.
- Verify no command reads a hostile/legacy pickle artifact; do not manually deserialize or inspect it.

No live financial mutation is needed at this checkpoint.

### Checkpoint B — before merging/accepting `mc-584r`

Human-only live proof on an expressly approved disposable test household:

- Set the dedicated mutation opt-in and exact household ID, then run only `make test-live-mutation`.
- Confirm the suite refuses wrong/missing household IDs and that `MONARCH_LIVE_TESTS` alone cannot select mutation tests.
- In the web UI, verify only the uniquely marked fixture account/transaction changed and both were removed afterward.
- Inspect the restricted recovery manifest for sufficient cleanup instructions and absence of credentials/financial payloads.
- If setup/cleanup is ambiguous, stop automation and recover manually; never rerun blindly.

### Checkpoint C — after the P1 read surface (`mc-ppai`)

Use bounded, read-only live commands against a willing test account and compare semantics with the UI:

- Null/missing relationships and actual transaction pending state.
- Transaction filters and requested-versus-returned detail IDs.
- Account type IDs, date ranges, snapshots, and unknown refresh IDs.
- Institution disconnected/update-required states and subscription unavailable-vs-false behavior.
- Holdings eligibility, account attribution, fixed fanout behavior, and absence of unsupported monetary totals.

Record only sanitized structural findings. Do not retain raw financial payloads in the repository or logs.

### Checkpoint D — after tags, splits, and attachments

For each PR, use one known disposable/restorable transaction and explicit `--allow-mutations`:

- Verify tag replace/clear and restore the original set.
- Verify split signed totals, replacement/readback, then restore or delete the disposable transaction.
- Upload a small non-sensitive fixture, confirm no Monarch credential reaches the media host, and inspect the attachment in the UI.
- Test dry-run separately and confirm it performs no authentication/network access.

Do not manufacture live timeouts to test ambiguity; mocked transport tests are safer. If a real timeout occurs, inspect before retrying.

### Checkpoint E — after review state, receipt inbox, and cookie auth

- **Review state:** use a restorable test transaction; confirm category/merchant are unchanged and both intent directions match the UI.
- **Receipt inbox:** upload a non-sensitive synthetic receipt once, verify the initial inbox state manually, and do not infer final matching or rerun after uncertainty.
- **Cookie auth:** import via protected file or stdin, verify `status`, `doctor/ping`, logout, keyring/JSON permissions, and that no `~/.mm` pickle is created. A human should handle browser-derived cookies and CAPTCHA-related steps.

### Checkpoint F — household ownership

Before `mc-iarh`/`mc-bf8f`, a human reviews the stable upstream release and the privacy allowlist. Then, on a disposable transaction:

- Confirm member IDs correspond to the intended household member without exposing extra profile data.
- Assign a member and verify readback.
- Test Shared only if the upstream proving signal is understood; otherwise confirm the CLI returns ambiguity rather than false success.
- Restore ownership manually and verify in the UI.

### Checkpoint G — credit-history decision

A human approves whether the dedicated research opt-in may be run, reviews the sanitized field/type/state summary, and signs off on the go/no-go rationale. Never check in raw responses, scores, names, profile data, or third-party IDs.

### Final release checkpoint — after schemas, live smoke, and capabilities

- Build/install the wheel and prove schema files are packaged and resolvable by their URNs.
- Run `make verify` and the isolated smoke-install target.
- Run only the bounded read-only live suite, then separately run the disposable mutation suite if release policy requires it.
- Diff the canonical capabilities manifest intentionally; verify generation performs no auth lookup, prompt, network call, or file write.
- Confirm normal CI and `MONARCH_LIVE_TESTS` cannot collect live mutation tests.
- Inspect the test household and any recovery manifests for leftover fixtures before release.
