# Research: Jev and its potential for `crcatala/monarch-cli`

**Research date:** 2026-09-18. External claims are labeled vendor or independent and repo-fit recommendations remain hypotheses.

---

## Evidence status (parent-verified source synthesis)

The parent agent fetched and reviewed the TypeSafe home page, launch post, official API/concepts documentation, the vendor workflow-evaluations site, and Archer Hume's independent architecture analysis on 2026-09-18. The facts below distinguish vendor claims from independent observations and do not treat valid typed output as semantic correctness.

- **Vendor positioning:** TypeSafe describes System One Models as models for fast, structured decisions that software can use directly. Jev is its first public/flagship System One Model. The documented interface is structured state in and typed decisions/probabilities out, rather than free-form generated text. *(Vendor: https://typesafe.ai; https://typesafe.ai/blog/introducing-system-one-models-and-jev; https://docs.typesafe.ai/concepts/system-one.)*
- **API contract:** `POST https://api.typesafe.ai/v1/systemone` with bearer authentication and model alias `jev-latest`. A request evaluates a string, JSON object, or array of text values against named typed questions. *(Vendor: https://docs.typesafe.ai/api.)*
- **Question primitives:** `Noul` returns a yes/no probability; `Choice` returns a selected caller-defined option and a full distribution; `Score` returns a probability-weighted value over an ordered caller-defined rubric, with a legend, distribution, and derived confidence. Choice/Score confidence is derived from the distribution, not an independent correctness guarantee. *(Vendor: https://docs.typesafe.ai/api; https://docs.typesafe.ai/confidence.)*
- **Composition model:** TypeSafe recommends narrow atomic questions, independent questions in parallel over shared state, deterministic control flow and side effects in application code, and confidence/probability thresholds that route uncertain or high-risk cases to review. Jev is documented as text-only and not a generator of prose, code, or reasoning explanations; it is not an autonomous agent. *(Vendor: https://docs.typesafe.ai/concepts/how-to-build-with-system-one; https://docs.typesafe.ai/concepts/state.)*
- **Performance/economics:** TypeSafe's launch post reports roughly 70–500 ms workflow latency, $0.042 per million input tokens ($42 per billion), and free output tokens, plus larger workload-specific speed/cost comparisons. These are vendor-reported early-access/workflow claims, not independent guarantees; the post discloses benchmark-selection and reference-model caveats. *(Vendor: https://typesafe.ai/blog/introducing-system-one-models-and-jev.)*
- **Evaluations:** `https://evals.typesafe.ai` demonstrates code-defined workflows where the model answers narrow questions and ordinary code makes the final decision (for example, expense-claim review). It is vendor-controlled evidence, not by itself an independent benchmark.
- **Independent analysis:** Archer Hume's post and linked evidence report behavior consistent with shared-state decision inputs, typed probability readouts, question/option interactions, and low upstream service times. It explicitly labels deeper claims about causal transformers, sparse MoE, KV sharing, and exact readout architecture as black-box inference; those details must not be presented as confirmed TypeSafe implementation facts. *(Independent: https://archerhume.com/posts/jevs-architecture-unmasked; https://archerhume.com/research/jev/evidence.json.)*
- **Operational caveat:** calibration is a property of groups of predictions, not a guarantee for an individual case. A type-safe answer can still be wrong. Any safety-, financial-, health-, or merge-critical integration therefore needs deterministic gates, domain-held-out evaluation, threshold calibration, logging, and human/strong-model escalation.

## 1. Executive Summary

**What we know for certain:** `monarch-cli` is an unofficial, read-only-by-default Python CLI
(and, intentionally, an AI-agent-oriented tool) for the Monarch Money personal-finance
platform. `[REPO]` It has an unusually disciplined safety model: every command declares an
explicit effect (`read_only`, `preview`, `remote_authentication`, `remote_mutation`,
`local_credential_change`), remote mutations require a per-invocation `--allow-mutations`
flag, mutations never auto-retry, and an uncertain mutation outcome is reported as an
`ambiguous` result under a versioned `mutation-outcome.v1` envelope with a distinct exit
code. `[REPO]`

**What still requires repo-specific validation:** whether TypeSafe's access/data terms, thresholds, and accuracy are acceptable for personal-finance data. The external Jev facts are sourced above; recommendations remain capability- and privacy-gated.

**Bottom-line potential impact (conditional):** *If* Jev verifiably provides strong
tool-use/structured-output/code-reasoning under a data-handling model acceptable for
personal financial data, the highest-value use of it here is **not** to swap out an existing
model in a fixed pipeline (this repo has essentially no model dependency today `[REPO]`).
It is to add **new, safety-preserving capabilities the repo does not have**: a
natural-language **read-only query/insight layer** that *compiles to the CLI's existing
tokenized read commands*, a **human-in-the-loop categorization assistant** for the
`needs_review` queue, and a **repo-native coding-agent workflow** for contract-preserving
change (schemas, transformers, mutation-outcome tests). The repo's own design — effect
taxonomy, dry-run previews, tokenized verification commands, non-interactive exit codes —
is unusually well-suited to be driven safely by an agent, which is why the opportunity is
real; but the opportunity is gated on validating privacy, deployment, and domain accuracy for personal-finance data.

---

## 2. Technical explanation of Jev and its capabilities

## Evidence status (parent-verified source synthesis)

The parent agent fetched and reviewed the TypeSafe home page, launch post, official API/concepts documentation, the vendor workflow-evaluations site, and Archer Hume's independent architecture analysis on 2026-09-18. The facts below distinguish vendor claims from independent observations and do not treat valid typed output as semantic correctness.

- **Vendor positioning:** TypeSafe describes System One Models as models for fast, structured decisions that software can use directly. Jev is its first public/flagship System One Model. The documented interface is structured state in and typed decisions/probabilities out, rather than free-form generated text. *(Vendor: https://typesafe.ai; https://typesafe.ai/blog/introducing-system-one-models-and-jev; https://docs.typesafe.ai/concepts/system-one.)*
- **API contract:** `POST https://api.typesafe.ai/v1/systemone` with bearer authentication and model alias `jev-latest`. A request evaluates a string, JSON object, or array of text values against named typed questions. *(Vendor: https://docs.typesafe.ai/api.)*
- **Question primitives:** `Noul` returns a yes/no probability; `Choice` returns a selected caller-defined option and a full distribution; `Score` returns a probability-weighted value over an ordered caller-defined rubric, with a legend, distribution, and derived confidence. Choice/Score confidence is derived from the distribution, not an independent correctness guarantee. *(Vendor: https://docs.typesafe.ai/api; https://docs.typesafe.ai/confidence.)*
- **Composition model:** TypeSafe recommends narrow atomic questions, independent questions in parallel over shared state, deterministic control flow and side effects in application code, and confidence/probability thresholds that route uncertain or high-risk cases to review. Jev is documented as text-only and not a generator of prose, code, or reasoning explanations; it is not an autonomous agent. *(Vendor: https://docs.typesafe.ai/concepts/how-to-build-with-system-one; https://docs.typesafe.ai/concepts/state.)*
- **Performance/economics:** TypeSafe's launch post reports roughly 70–500 ms workflow latency, $0.042 per million input tokens ($42 per billion), and free output tokens, plus larger workload-specific speed/cost comparisons. These are vendor-reported early-access/workflow claims, not independent guarantees; the post discloses benchmark-selection and reference-model caveats. *(Vendor: https://typesafe.ai/blog/introducing-system-one-models-and-jev.)*
- **Evaluations:** `https://evals.typesafe.ai` demonstrates code-defined workflows where the model answers narrow questions and ordinary code makes the final decision (for example, expense-claim review). It is vendor-controlled evidence, not by itself an independent benchmark.
- **Independent analysis:** Archer Hume's post and linked evidence report behavior consistent with shared-state decision inputs, typed probability readouts, question/option interactions, and low upstream service times. It explicitly labels deeper claims about causal transformers, sparse MoE, KV sharing, and exact readout architecture as black-box inference; those details must not be presented as confirmed TypeSafe implementation facts. *(Independent: https://archerhume.com/posts/jevs-architecture-unmasked; https://archerhume.com/research/jev/evidence.json.)*
- **Operational caveat:** calibration is a property of groups of predictions, not a guarantee for an individual case. A type-safe answer can still be wrong. Any safety-, financial-, health-, or merge-critical integration therefore needs deterministic gates, domain-held-out evaluation, threshold calibration, logging, and human/strong-model escalation.

### Best-fit and poor-fit workloads

Jev is best suited to classification, detection, routing, scoring, ranking/retrieval, verification, and semantic feature extraction when the application can define the answer space in advance and retain control of side effects. It is a poor fit for open-ended response generation, code generation, unconstrained agent loops, explanations, or multimodal input under the currently documented interface. The repo-specific recommendations below should therefore be read as integration hypotheses until tested on representative data.

## 3. Repo-Specific Opportunities

The following are grounded in directly verified repo facts. For each, note the **existing safety
substrate** that makes an agent-driven feature feasible *without* weakening the repo's guarantees.

### 3.1 Repo baseline (verified) — what exists today

- **Command surface** `[REPO]`: `auth` (login/status/logout/ping/doctor/setup), `accounts`
  (list/refresh), `transactions` (list/get/update/batch-update), `budgets list`,
  `cashflow summary`, `categories list`. No create/delete, no tags, no rules, no goals, no
  investments, no net-worth command, no reporting/insight command.
- **Effect taxonomy & authorization** `[REPO]`: `Effect = {READ_ONLY, PREVIEW,
  REMOTE_AUTHENTICATION, REMOTE_MUTATION, LOCAL_CREDENTIAL_CHANGE}`; the CLI is read-only
  by default; `remote_mutation` requires `--allow-mutations` **in the global-option position**;
  authorization is process-global for the invocation only and is **never** configurable by file
  or environment variable; blocked mutation → exit `3` `MUTATION_BLOCKED`.
- **Mutation outcome contract** `[REPO]`: `mutation-outcome.v1` envelope with
  `succeeded|failed|ambiguous|partial`, exit codes `0/1/4/4`; per-item `result`/`error`
  (sanitized); a **required `verification` object with a tokenized safe command** whenever any
  item is ambiguous; `MUTATION_AMBIGUOUS` reserved for ambiguous items.
- **Retry/ambiguity policy** `[REPO]`: reads retry with exponential backoff + jitter; **mutations
  execute exactly once** (`NO_RETRY`); `IDEMPOTENCY_KEY` and `READ_AFTER_WRITE` are reserved and
  refused until operation-specific tests exist; timeouts/disconnects/Ctrl-C after dispatch →
  `MutationAmbiguousError` (exit `4`).
- **Non-interactive policy** `[REPO]`: `--non-interactive` / `MONARCH_NON_INTERACTIVE` /
  `non_interactive` config; a would-be prompt fails **before any input read** with exit `5`
  `PROMPT_BLOCKED` and an actionable `details.remedy`; non-interactive mode **never** authorizes
  mutations and **never** auto-answers confirmations.
- **Stable machine schemas** `[REPO]`: normalized `accounts`/`transactions` fields are documented
  as a stable contract; `--raw` bypasses transformation; `--quiet` emits IDs only; `--ndjson`
  for streaming; auto-JSON when piped.
- **Date presets & filtering** `[REPO]`: rich tri-state boolean filters (pending, needs_review,
  split, recurring, hidden, mint-import, synced-from-institution, has-attachments, has-notes),
  repeatable account/category/tag, visibility scope, search, `--preset` ranges.
- **Auth/credential handling** `[REPO]`: token resolution order `MONARCH_TOKEN` → keyring →
  `session.json` (POSIX `0600`); legacy pickle sessions are **never read** (presence-only
  detection); `auth setup` documents that `MONARCH_TOKEN` is visible to `ps`/`/proc`.
- **Adapter seam** `[REPO]`: all `monarchmoney`/`monarchmoneycommunity` imports are isolated in
  `core/adapter.py` (protects the codebase from upstream drift). `pyproject.toml` declares the
  dependency as `monarchmoneycommunity` while `adapter.py` imports the `monarchmoney` namespace —
  consistent with a drop-in namespace package, but worth confirming `[INFERENCE]`.
- **Testing substrate** `[REPO]`: unit suite (`-m "not live"`), gated read-only live suite, and a
  separately gated **live mutation contract suite** that mutates only a self-created disposable
  fixture and journals recovery manifests under `.monarch-live-mutation-recovery/`.
- **Release/verification tooling** `[REPO]`: `make verify` (format/lint/typecheck/test),
  `make smoke-install` (isolated wheel install), `make prepublish`, TestPyPI→PyPI flow documented
  in `docs/RELEASING.md`.

### 3.2 New customer-facing features

**A. Read-only natural-language query ("`monarch ask`" style).** `[INFERENCE]`
A user asks *"how much did I spend on groceries last quarter vs the year before?"*; the system
maps it to an **existing tokenized read-only command** (`monarch cashflow summary --preset ...`,
`monarch transactions list --category ... --start ... --end ...`) and presents the answer plus the
exact command it ran. Why this fits the repo: the whole surface is enumerable and read-only by
default `[REPO]`, so an agent can be constrained to emit *only* validated read commands; no new
mutation authority is introduced.

**B. Monthly narrative insight report.** `[INFERENCE]` Generate a human-readable summary
("what changed, what's over budget, what's unusual") from `budgets list`, `cashflow summary`, and
`transactions list` output. Pure read-only; produces text, not side effects.

**C. Needs-review categorization assistant.** `[INFERENCE]` The repo already exposes a
`--needs-review` filter and stable `category`/`category_id` fields `[REPO]`. An assistant proposes
a category per pending item; the user approves; application goes through the **existing**
`transactions batch-update --category ... --dry-run` then `--allow-mutations` path. This reuses the
mutation-outcome envelope and never needs new mutation authority.

**D. Anomaly / duplicate / subscription-detection explanations.** `[INFERENCE]` Runs over
`transactions list` output to flag likely duplicates and recurring charges; read-only. (The repo
already models `is_recurring` and `is_split` as fields/filters but surfaces no detection feature
`[REPO]`.)

### 3.3 Backend / automation capabilities

**E. Ambiguity-recovery assistant.** `[INFERENCE]` When a mutation returns `ambiguous` (exit `4`),
the envelope already contains a required `verification` object with a tokenized safe command `[REPO]`.
An agent can execute that read-only verification, compare before/after, and report whether the write
landed — **without ever retrying blindly**, honoring the repo's explicit "never retry an ambiguous
mutation" rule.

**F. Scheduled non-interactive digest.** `[INFERENCE]` Via `--non-interactive` + `auth` via keyring
or injected `MONARCH_TOKEN` `[REPO]`, produce a recurring read-only digest/alert job. No new remote
authority needed; the exit-code contract (`3/4/5`) already makes automation failures unambiguous.

**G. Human-approved batch re-categorization pipeline.** `[INFERENCE]` Chain A/C/E: propose →
preview (`--dry-run`) → authorize (`--allow-mutations`) → interpret `mutation-outcome.v1` →
verify on ambiguity. The repo's preview/mutation separation is a ready-made "propose vs commit" split.

### 3.4 Developer tooling (repo-native)

**H. Contract-preserving coding agent.** `[INFERENCE]` Use Jev to make changes that must preserve
the documented contracts: extend `mutation-outcome` (a v2 would require new version handling `[REPO]`),
add transformers that tolerate nullable/malformed upstream shapes, add commands that must register
effect metadata (a test fails any command lacking it `[REPO]`). The repo's strict `mypy`, ruff, and
`make verify` gate `[REPO]` gives an agent a tight, checkable loop.

**I. Adversarial test synthesis.** `[INFERENCE]` Generate tests for the repo's *safety invariants*:
mutation blocked without `--allow-mutations`, effect-metadata completeness, no-retry-for-mutations,
`MUTATION_AMBIGUOUS` reserved-only-for-ambiguous, `PROMPT_BLOCKED` precedes any input read, sanitized
error objects never leaking credentials/raw bodies. These invariants are explicitly and repeatedly
stated in the source `[REPO]` and are exactly the kind of thing worth fuzzing.

**J. Fixture/transformer fuzzing.** `[INFERENCE]` The transformers define explicit null/missing/
present-but-null tolerance rules `[REPO]`; an agent can synthesize upstream response shapes to prove
those rules.

### 3.5 Admin / operations use cases

**K. PR/change policy reviewer.** `[INFERENCE]` A reviewer focused on this repo's invariants:
read-only default, per-invocation-only mutation authorization, single-attempt mutations, non-interactive
prompt refusal, exit-code stability (`0/1/3/4/5`), and "breaking contract change requires a new schema
version" `[REPO]`.

**L. Ops runbook / error triage assistant.** `[INFERENCE]` Map a user's exit code and structured error
to the documented remedy: `3`→add `--allow-mutations` in the right position; `4`→verify before retry;
`5`→use explicit values/`--stdin` or authenticate via `MONARCH_TOKEN`; legacy pickle present→re-login
and delete the file manually `[REPO]`.

**M. Security-posture review.** `[INFERENCE]` Assess credential handling (keyring vs file `0600` vs
`MONARCH_TOKEN` leakage surface) and whether any workflow risks committing tokens or financial data
(`docs/RELEASING.md`'s `~/.pypirc` guidance, live-test credential rules `[REPO]`).

---

## 4. Recommendations (Huge / Medium / Low predicted impact)

> All recommendations are **conditional on the §2.3 verifications**. Complexity/disruption are judged
> against the repo as it exists today. "Architectural disruption" = how much of the current design
> would have to change.

### Huge predicted impact

**H1 — Read-only natural-language query & insight layer ("ask" / "insights").**
- **Expected value:** Highest-magnitude *new* customer-facing capability; turns the CLI's already-stable
  read schemas into a conversational product without new mutation authority. Broadest audience lift.
- **Implementation complexity:** Medium-high (new intent→command compiler, schema-constrained output,
  rendering; but it reuses existing commands).
- **Architectural disruption:** Low-to-medium. Adds a layer *above* existing commands; the effect
  taxonomy and mutation contract stay intact. Requires a new "expansion" module that can only emit
  validated `READ_ONLY`/`PREVIEW` invocations.
- **Dependencies:** verified structured/tool output (2.3.2–3), latency acceptable for interactive use
  (2.3.7), cost model compatible with a free MIT tool (2.3.8), and a data-handling policy fit for
  financial data (2.3.11).
- **Risks:** hallucinated numbers presented as fact; leaking account data to a third party; the model
  emitting a command the user didn't intend. Mitigations the repo already enables: always show and
  execute the **tokenized read-only command**, never free-form SQL/API; keep outputs grounded in CLI
  JSON; the read-only default means no model mistake can mutate state.
- **Next experiment:** offline prototype that maps 20 hand-written finance questions to validated
  `monarch ...` read commands and compares the executed command against a human-expected command;
  measure intent accuracy and command validity rate.

**H2 — Human-in-the-loop needs-review categorization assistant.**
- **Expected value:** High. Attacks the most laborious real workflow (clearing the review queue) and is
  the clearest "new" feature beyond read-only reporting.
- **Implementation complexity:** Medium (build on `transactions list --needs-review` + `batch-update
  --dry-run`/`--allow-mutations`).
- **Architectural disruption:** Low. No new effects; reuses `mutation-outcome.v1`.
- **Dependencies:** verified classification quality on real merchant strings; strict output constraints
  (category **IDs**, not free text); data-handling fit (2.3.11).
- **Risks:** wrong categorization applied at scale; the classic "agent + write access" hazard. Mitigate
  with mandatory `--dry-run` preview, explicit human approval before `--allow-mutations`, bounded batch
  sizes, and honoring the ambiguity/verify rule.
- **Next experiment:** shadow-mode run over a user's `needs_review` queue producing **suggestions only**;
  measure top-1 category accuracy vs the user's actual choice before enabling any write path.

**H3 — Repo-native coding agent for contract-preserving work.**
- **Expected value:** High developer velocity on a repo whose value *is* its contracts; the codebase is
  small, typed, and hard-gated (`mypy` strict, ruff, `make verify`) `[REPO]`, making it a good agent target.
- **Implementation complexity:** Low-to-medium to adopt; high to trust.
- **Architectural disruption:** None to the product; changes process.
- **Dependencies:** verified code quality on this repo's Python/Typer/asyncio patterns and on its
  invariant style (2.3.4); access/licensing allowing code ingestion; data policy (source is public,
  which eases the privacy concern).
- **Risks:** silent weakening of safety invariants (e.g., adding a mutation path without `--allow-mutations`
  gating, or retrying mutations). Mitigate by requiring the invariant test suite (see M4/I) as a
  merge gate.
- **Next experiment:** have the agent implement one *low-risk* change end-to-end (e.g., a new read-only
  transformer + its null-tolerance tests) and measure whether `make verify` passes without human edits
  and whether any invariant test was weakened.

### Medium predicted impact

**M1 — Ambiguity-recovery/verification assistant.**
- **Expected value:** Medium-high operational value; directly leverages the envelope's existing
  `verification` object `[REPO]`.
- **Complexity:** Low-medium. **Disruption:** Low (read-only). **Dependencies:** tool use (2.3.2) to
  run the tokenized command.
- **Risks:** a model "helpfully" retrying — must be explicitly forbidden by design.
- **Next experiment:** replay recorded ambiguous outcomes and check the assistant never issues a write
  and always runs the read-only verification first.

**M2 — Scheduled non-interactive digest/alerts.**
- **Expected value:** Medium; retention/serendipity value from a finance CLI.
- **Complexity:** Low-medium. **Disruption:** Low. **Dependencies:** cost for scheduled runs (2.3.8),
  credentials via keyring/`MONARCH_TOKEN` `[REPO]`. **Risks:** secret leakage in schedulers; noisy
  digests. **Next experiment:** one cron-style read-only run in `--non-interactive` mode with a fixture
  account; confirm exit codes are interpreted correctly.

**M3 — Ops/PR policy reviewer for repo invariants.**
- **Expected value:** Medium; protects the project's main asset (its safety contract).
- **Complexity:** Low-medium. **Disruption:** None. **Next experiment:** run it against 10 recent-style
  diffs, including deliberately injected violations, and measure detection rate/false positives.

**M4 — Adversarial test & fixture synthesis for transformers and invariants.**
- **Expected value:** Medium; raises confidence in the stable-schema and ambiguity guarantees.
- **Complexity:** Low-medium. **Disruption:** None (tests only). **Dependencies:** code-gen quality.
  **Next experiment:** generate null/malformed upstream shapes for `transform_transaction_detail` and
  confirm they either normalize or raise the documented typed errors `[REPO]`.

### Low predicted impact

**L1 — Documentation/help Q&A ("how do I do X").** Low value; the README is already comprehensive `[REPO]`.
**L2 — Changelog / release-note drafting.** Convenience only; `CHANGELOG.md` conventions are simple `[REPO]`.
**L3 — Config/security posture review.** Lower frequency; `auth setup`/`auth doctor` already cover most of it `[REPO]`.

---

## 5. Prioritized Roadmap, Open Questions, Limitations

### 5.1 Prioritized roadmap (conditional)

1. **Verify first (blocking gate).** Resolve §2.3 items 1, 3, 7, 8, 9, 11 from primary sources
   (TypeSafe docs/API terms, `evals.typesafe.ai` methodology, license/terms). Do not start H-tier
   work on unverified capability or data-handling assumptions.
2. **H1 read-only query layer — prototype offline.** No live data, no network integration; validate the
   NL→tokenized-read-command compiler (§5.3 experiment).
3. **H2 categorization assistant in shadow mode.** Suggestions only; measure accuracy before any write path.
4. **H3 coding agent on one low-risk change**, gated by `make verify` + invariant tests.
5. **M1 ambiguity assistant**, then **M4 invariants/fixtures**, then **M3 policy reviewer**.
6. **M2 scheduled digest**, then L-tier conveniences.

### 5.2 Open questions (remaining integration)

- Is Jev a model, an agent system, or a product wrapping other models? What exactly are "System One models"?
- Does Jev offer schema-constrained/structured output and reliable tool calling?
- Access model: public API, waitlist, SDK, or local weights? Rate limits? Commercial embedding allowed?
- Pricing/throughput/latency: viable for an interactive CLI and for a free MIT project?
- Data handling: retention, training-use, sub-processors, and any on-prem/self-host option — **decisive
  for personal financial data**.
- Are the evaluation claims on `evals.typesafe.ai` independent, reproducible, and contamination-controlled?
- What does the third-party "architecture unmasked" analysis actually claim, and is it corroborated?
- What online discourse/dissent exists (benchmark disputes, safety concerns, cost complaints)?
- Any licensing restriction on outputs that conflicts with this repo's MIT license `[REPO]`?

### 5.3 Limitations of this report

- **Source note:** this child runtime had no web tools; the parent fetched and verified the external dossier used above. Repository-fit claims remain hypotheses and require local evaluation.
- **No calendar date verified**, so "recency" of any future sources must be checked separately.
- Repository findings are limited to files actually read: `README.md`, `pyproject.toml`, `CHANGELOG.md`,
  `Makefile`, `AGENTS.md` (absent), `docs/mutation-outcomes.md`, `docs/RELEASING.md`,
  `src/monarch_cli/main.py`, `commands/{auth,accounts,transactions,budgets,cashflow}.py`,
  `core/{adapter,config,operations,mutation_outcomes,retry,async_utils,exceptions,error_handler,prompting,session}.py`,
  `output/__init__.py`, `services/accounts.py`, `transformers/transactions.py`. Other files
  (e.g., `core/dates.py`, `output/plain.py`, `transformers/accounts.py`, `transformers/cashflow.py`,
  `core/nesting.py`, tests) were not read and may contain additional relevant detail.
- Recommendations are **capability-gated `[INFERENCE]`**, not proven value.

---

## 6. Safety & Privacy Implications (repo-grounded)

The biggest non-capability risk is **data handling**, because this tool handles personal financial data
and session credentials `[REPO]`.

- **What must never leave the trust boundary:** session tokens (keyring/`MONARCH_TOKEN`/`session.json`)
  and raw credentials. The repo already treats tokens as sensitive and never reads legacy pickle files `[REPO]`;
  any agent integration must preserve that. The repo's own `auth setup` notes `MONARCH_TOKEN` is visible
  via `ps`/`/proc` `[REPO]`.
- **Transaction/account data is personal financial data.** H2/H1 imply sending merchant strings, amounts,
  balances, and account names to a model. This requires a verified retention/no-training/processing
  posture (§2.3.11) or a local/self-hosted option before it can be considered for real users.
- **Design property to preserve:** the read-only-by-default + explicit `--allow-mutations` +
  single-attempt + ambiguous-outcome model `[REPO]` is the natural containment mechanism. An agent that
  can only emit validated read commands (H1) or only propose changes that a human authorizes (H2) cannot
  silently mutate financial state.
- **Third-party ToS risk:** this is an *unofficial, community-maintained* project explicitly not
  affiliated with Monarch Money `[REPO]`; introducing automated third-party processing of Monarch-derived
  data may have its own upstream-terms implications that need separate review.

---

## 7. Sources

### Kept (repository — directly verified this run)

Files read in `/tmp/jev-research.1FrXpC/monarch-cli` and used as primary evidence for all `[REPO]` claims:
`README.md`, `pyproject.toml`, `CHANGELOG.md`, `Makefile`, `docs/mutation-outcomes.md`,
`docs/RELEASING.md`, `src/monarch_cli/main.py`, `src/monarch_cli/commands/{auth,accounts,transactions,budgets,cashflow}.py`,
`src/monarch_cli/core/{adapter,config,operations,mutation_outcomes,retry,async_utils,exceptions,error_handler,prompting,session}.py`,
`src/monarch_cli/output/__init__.py`, `src/monarch_cli/services/accounts.py`,
`src/monarch_cli/transformers/transactions.py`. (Local paths; no URL.)

### External sources — parent-fetched and reviewed
- TypeSafe: https://typesafe.ai
- Introducing System One Models and Jev: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- TypeSafe API/concepts/confidence docs: https://docs.typesafe.ai/api, https://docs.typesafe.ai/concepts/system-one, https://docs.typesafe.ai/confidence
- TypeSafe workflow evaluations: https://evals.typesafe.ai
- Independent architecture analysis and evidence: https://archerhume.com/posts/jevs-architecture-unmasked and https://archerhume.com/research/jev/evidence.json

### Rejected / deprioritized### Rejected / deprioritized

- None. No external sources were retrieved, so none were filtered this run.

---

## 8. Next Steps

1. **Fetch and check the four provided sources** (and their linked primary docs/terms) with a web-capable
   agent: TypeSafe intro post, `evals.typesafe.ai` methodology page, the Archer Hume post, and TypeSafe's
   API/terms/license/pricing pages. Resolve §2.3 and §5.2.
2. **Vendor-claim vs independent-evidence split:** record what TypeSafe claims (capabilities, evals,
   pricing, access) separately from what independent reviewers report.
3. **Contradictions log:** capture any disputes (benchmark disputes, architecture disputes, cost/safety
   critiques) explicitly rather than averaging them.
4. **Then** run the §5.1 experiments (H1 offline prototype, H2 shadow-mode accuracy, H3 gated coding task).
5. **Data-handling attestation** before any feature touches real user data (§6).
