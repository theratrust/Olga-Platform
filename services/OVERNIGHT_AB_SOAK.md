# DEV overnight baseline / configurable candidate soak

This separate runner has no bot integration, database or Telegram ports. Default
invocation is a dry-run: validates pinned sources and six synthetic scenarios;
no credentials, SDK/client, network or output creation. Explicit live settings
are fixed to z-ai/glm-5.2, OpenRouter, OPENROUTER_API_KEY, timeout 60, generator
350 tokens. Evaluators use existing qualified GLM 5.2 / 4000 / low / 60 configs,
prompt/contracts and bounded structural repair unchanged.

Baseline source is `git show 176cb07c0941ffb53c5d34f99e9cb86def6ada59:prompts/coaching.py`.
Its fixed SHA-256 is f319b7b333f880a818d419f88035226b0c907e8cc70da872a20ecee8c2c08284.
A container without git may read a byte-identical read-only snapshot supplied by
`--baseline-source`; the fixed digest is required. Candidate source is read from
the current working tree; removing only the Candidate A response-shape block must
recover the entire baseline source exactly. Both modules load in isolated memory,
without patching imports or switching the main worktree. Method/context building
is the same. Shared generator request/headers/extraction remain identical.
Source fingerprints are checked before each turn/scenario; drift stops the soak.
Candidate prompt/test fingerprints, scenario digest, baseline manifest bindings
and all service/prompt/method fingerprints are retained in run metadata.

5–10 paired trials, default 10. Odd: BASELINE then the configured candidate ID; even: reverse.
Each variant executes six fresh independent scenario histories/correlations.
The first generator failure ends that scenario only, without retry; later
scenarios/trials continue as independent observations. Existing SDK transport
retry behavior is unchanged; no new same-call retry is added. Attempts count SDK
invocations, not underlying HTTP exchanges. Failed generator turns are never
evaluated. Successful turns run both existing observational evaluators.

Every attempt is fsync/flush persisted to an exclusively created mode-0600 JSONL
before evaluation. A separate evaluator event follows. Correlations and content
are hashes only. Metadata consists of fixed identifiers, scalar diagnostic
presence/type/length/usage/status fields and safe evaluator projections. No raw
conversation, content, reasoning, refusal/tool arguments, reasons/evidence,
provider envelope, headers or credentials are serialized. Reasoning length is
the maximum available character length among exposed reasoning fields (not a
sum that might double-count aliases). Missing metadata has null values.
Primary failure precedence: provider/transport, zero choices, unexpected shape,
refusal/tool only, reasoning present with final empty, length terminated empty,
null, empty string, whitespace only, other. Primitive metadata retains overlaps;
classification does not infer truncation from token count alone.

One unique UTC/run-ID prefix owns JSONL, aggregate JSON, markdown summary,
initial PID/status JSON and terminal status JSON; prior files are never overwritten.
Initial status remains immutable; terminal status is a separate final receipt.
JSONL recovery accepts complete lines and ignores only an incomplete final line.
Malformed complete lines fail closed. A SIGKILL/power outage may leave only the
JSONL/status; `recover_events` and `summarize` can analyze it without re-execution.

Reliability includes every attempted generator call, scenario/turn/trial rates,
empty/failure classes, finish/reasoning distributions, token distributions and
latency. Wilson 95% proportion intervals and conservative Wilson-bound difference
estimates are labeled descriptive: calls are dependent within conversations,
so no significance claims follow. Historical Candidate A 33 calls/4 empty results
remain metadata, excluded from this fresh paired experiment's rates.

Coaching aggregates use final-valid evaluator results; incomplete scenarios may
contribute successful turns, with completion counts explicit. Consecutive Q03
reported for completed scenario trials is separate from all-observation metrics.
Existing descriptive low-score/repeated weakness/late-half rules are reused,
never changed. Paired quality comparison requires matching trial/scenario/turn,
both generator successes and final-valid quality outputs. Null scores and
insufficient-context labels are excluded from ordinal comparisons, with exclusion
counts. Higher scores/category are better; fewer Q02/Q03/Q05 flags are better.

Deterministic decision labels are experiment summaries, not evaluator verdicts:
- Reliability: after full run, at least 100 attempts per variant. Similar if
  absolute failure-rate difference <2 percentage points. Better/worse requires
  >=10 combined failures, >=5 percentage-point change, and risk ratio <=2/3 or
  >=1.5 respectively (baseline-zero risk ratio undefined). Otherwise inconclusive.
- Coaching: after full run, >=30 matched valid quality turns. Better requires at
  least two paired primary reductions: Q03 >=25%, low non-repetition >=25%, Q02
  >=25%, low progression >=20%, plus Candidate methodology all pass/accept/no hard
  fails; no increase in paired weak/Q07/Q08; naturalness/contextual-specificity
  paired mean drop <=0.1. Any Candidate methodology hard fail is worse. Otherwise
  at least two worsening primary counts and zero material improvements is worse;
  remaining adequate evidence is mixed. Insufficient data is inconclusive.

Run default dry-run:
`python3 tests/run_dev_overnight_ab_soak.py`

Authorized live command in the existing DEV container (no restart):
```sh
docker exec -w /app olga_bot_container_dev python tests/run_dev_overnight_ab_soak.py \
  --live --candidate-id CANDIDATE_B --model z-ai/glm-5.2 --base-url https://openrouter.ai/api/v1 \
  --api-key-env OPENROUTER_API_KEY --timeout 60 --paired-trials 10 \
  --baseline-source /app/.dev-backups/overnight-ab-baseline/176cb07c0941ffb53c5d34f99e9cb86def6ada59/coaching.py \
  --run-id <UTC_unique_run_id>
```
Detach via nohup with a unique DEV artifact run log and PID file. No secrets are
passed on the command line. Existing benchmark latency suggests 720 turns take
about 4.1 hours; failed scenarios shorten this, slow providers may extend it.
No automatic prompt/model/routing change or commit follows either conclusion.


## Candidate identity (labeling only)

LIVE requires explicit `--candidate-id CANDIDATE_B` (or `CANDIDATE_A` for an
A experiment). Dry-run defaults to `CANDIDATE`. IDs are uppercase stable tokens,
up to 64 characters, and cannot be `BASELINE`. The supplied ID names variant
events, isolated prompt modules, aggregate and paired keys, and rendered
conclusions, e.g. `CANDIDATE_B_QUALITY_WORSE`. Inconclusive labels remain generic.
Metadata records `candidate_id`, `candidate_prompt_sha256` and
`candidate_tests_sha256`; the fingerprint is associated with that ID. Historical
A metadata/artifacts are never rewritten. Analysis helper defaults remain
`CANDIDATE_A`, so historical A events can be read/recomputed unchanged. Explicit
candidate identity must be passed to analysis of other candidate events.

This parameter changes labeling and which candidate side is selected, never
pair matching conditions, calculations, thresholds, variant order, prompts,
request settings, retries, or evaluator behavior. `historical_candidate_a`
continues to describe actual earlier A evidence; it is not relabeled as B.


## Baseline-only checkpoint

When the working-tree prompt exactly equals the pinned baseline, source loading
accepts that identity and default dry-run remains usable. Distinct candidate
sources still require the existing response-shape-block-only difference check.
A baseline-only checkout does not start a new candidate or a live experiment.
