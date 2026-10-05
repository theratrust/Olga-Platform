# DEV observational response-quality shadow mode

Response quality has `derived_product_quality_criteria` provenance. It does not
qualify Olga methodology compliance. The methodology evaluator remains unchanged
and independent; no quality score can compensate for a methodology hard fail.
No observation is authorized for blocking, routing, regeneration, escalation or
changing the delivered candidate. Structural retry retries only the evaluator.


## Qualified DEV quality-shadow baseline

GLM 5.2 (`z-ai/glm-5.2`) is selected as the **QUALIFIED BASELINE candidate**
for DEV response-quality shadow evaluation. These operator-supplied frozen-run
results qualify a candidate for observation only, not methodology compliance.

Three frozen 22-case runs / 66 judgments:

- GLM overall_quality agreement: 58/66 = 87.9%.
- Sonnet overall_quality agreement: 57/66 = 86.4%.
- Both: 66/66 first-pass contract valid; zero final infrastructure failures.

GLM dimension agreement:

| Dimension | Agreement |
| --- | --- |
| contextual_specificity | 69.7% |
| progression | 89.4% |
| non_repetition | 84.8% |
| naturalness | 66.7% |
| question_quality | 86.4% |
| proportionality | 63.6% |

Persistent GLM semantic mismatches: `mild_extra_paraphrase` 3/3,
`missing_repetition_history` 3/3, and `justified_once` 2/3.
`Q03_REPETITIVE_STRUCTURE` and `Q08_OVERLONG_OR_UNDERDEVELOPED` each have
100% precision / 100% recall across 66 frozen judgments. Their higher-confidence
status remains diagnostic and is limited to these synthetic qualification runs.
Q01/Q04/Q06/Q07 have low precision and must be diagnostic only.
No quality result is authorized for blocking, routing or regeneration.
No quality score can compensate for a methodology hard fail.

The qualification harness remains a model-selection tool. The separate DEV
observational integration is documented in [SHADOW_MODE.md](SHADOW_MODE.md).

## Explicit opt-in configuration

Defaults (not applied to `.env.dev` by this change):

```dotenv
QUALITY_EVALUATOR_SHADOW_ENABLED=false
QUALITY_EVALUATOR_MODEL=z-ai/glm-5.2
QUALITY_EVALUATOR_MAX_TOKENS=4000
QUALITY_EVALUATOR_REASONING_EFFORT=low
QUALITY_EVALUATOR_TIMEOUT_SECONDS=60
QUALITY_EVALUATOR_BASE_URL=https://openrouter.ai/api/v1
```

Only the explicit value `true` (case-insensitive, surrounding whitespace ignored)
enables quality observations. Methodology `EVALUATOR_*` settings do not enable
quality evaluation. The only credential source is the existing
`OPENROUTER_API_KEY`; no credential is read at module import. Disabled observation
returns before credential lookup, prompt construction or model calls.

The exact existing fail-closed `services.evaluation.runtime.is_dev_runtime` guard
runs before dispatch and again in the worker. It uses module location and existing
DEV mount/database/environment identity. `/app`, DEV_DIRECT_CHAT or a configurable
boolean alone cannot prove DEV identity. Contradictory identity fails closed for
provider calls, while observation failure stays fail open for chat delivery.

## Independent bounded observation

`QualityShadowDispatcher` owns one ThreadPoolExecutor worker and at most one
outstanding observation. Saturation drops the observation with
`capacity_exceeded`; it never queues a backlog. Submission is non-awaiting.
Cancellation of its async observer does not release an active worker slot.
`disable()` rejects new work; `close()` rejects new work and drains active work.
Its worker and capacity are independent from methodology `ShadowDispatcher`.

The optional chat hook runs after the existing direct-delivery or moderation path
completes, alongside the methodology hook, with each exception contained separately.
DEV_DIRECT_CHAT behavior and generator prompt remain unchanged. Bot shutdown drains
both dispatchers. No containers are restarted and the feature remains disabled by
default until separately enabled.

The worker deep-copies only the last 20 ordered history messages. It uses the
unchanged quality prompt, strict contract and quality repair policy. It makes at
most two evaluator attempts: only deterministic structural failures are eligible
for the second attempt. No retry for valid quality judgments, evidence disagreement,
score/flag/overall inconsistency, transport, timeout or provider failures. Runtime
never loads synthetic gold, qualification outcomes or metrics, and never executes
any quality-based routing action.

## Privacy and logging

Events: `QUALITY_SHADOW_EVAL_SCHEDULED`, `QUALITY_SHADOW_EVAL_OK`,
`QUALITY_SHADOW_EVAL_RECOVERED`, `QUALITY_SHADOW_EVAL_FAIL`.
JSON logs contain only timestamp, `mode=quality_shadow`, evaluator model,
candidate SHA-256, hashed conversation-instance ID, validated six-dimension scores,
quality flag IDs, overall_quality, insufficient_context present Boolean,
first-pass/final contract validity, retry attempted/recovered, latency_ms and
allowlisted safe error kinds. Partial scheduling/failure events omit unavailable
fields. No raw user/candidate/history text, reason, evidence excerpts, provider
envelopes, reasoning, credentials, headers or environment containers are logged.
The active credential is redacted from metadata too. Only aggregates are returned
from runtime observation; no raw result or artifact is persisted. Logging failures
are contained. Q03/Q08 remain higher-confidence diagnostics on the frozen synthetic
corpus only; all flags and scores remain observational, with no routing authorization.

## Conversation-instance correlation

`session_hash` now identifies one conversation instance created by `/new`, rather
than a Telegram user. Each `/new` generates a fresh random UUID correlation value
stored only as `shadow_conversation_id` in the existing in-memory FSM data. Normal
AI_CHAT messages reuse it; if it is absent or empty/invalid, the handler generates
and stores a defensive fallback. Both methodology and quality observers receive
the same conversation value, never bare user_id, and existing runtimes emit only
its SHA-256 hash. The raw value is never logged, shown to the user, added to the
generator prompt, or persisted in the database. Archetype and other FSM data are
preserved. No evaluator schema, semantics, route, or retry policy changes.

A process restart loses the in-memory correlation value; the fallback starts a new
correlation instance. Historical user-based hashes cannot retroactively establish
conversation boundaries. Hashes remain correlation identifiers, not anonymization.
