# Synthetic DEV conversation benchmark

The local benchmark generates scripted Russian multi-turn conversations and runs
both existing observational shadow evaluators on each generated candidate. It is
for descriptive before/after evidence, not ground truth, gold qualification or
methodology acceptance. Quality cannot compensate for methodology hard fail.
There is no binary systematic-pattern verdict and no routing authorization.

The frozen benchmark input has six synthetic scenarios, six turns each (36 turns):
relocation identity, work/autonomy, partner influence, space for "я не знаю",
repeated uncertainty, and stuckness/action. Each record declares
`synthetic_dev_conversation_benchmark` provenance. No expected evaluator labels,
real-user data or modifications to frozen evaluator corpora are included. Strict
closed JSON, unique scenario IDs and 5–8 Russian turns are required.

## Shared generator guarantee

`services/coaching_generator.py` is used by both `ai_chat_handler` and the runner.
It calls the unchanged `build_coaching_prompt`, builds one system instruction plus
the supplied ordered history, requests the chosen model with max_tokens=350 by
default and the existing OpenRouter referer/title headers, and extracts
`response.choices[0].message.content`. It adds no temperature, schema, reasoning
or response postprocessing. Bot generation settings, archetype, acknowledgements,
moderation, delivery and DEV_DIRECT_CHAT behavior remain unchanged.

Each scenario gets fresh in-memory history and a random correlation ID. The
benchmark uses fixed synthetic first_name="Тест" and the scenario archetype.
Each user turn is appended before generation. A copy of the last 20 ordered
messages is the generator/evaluator context. The candidate is appended to the
in-memory history before evaluation, but evaluation receives that pre-candidate
snapshot, exactly like chat; the response cannot appear in its own context.
Later scripted user messages are fixed, not adaptively generated model turns.

A generator failure aborts that scenario without inventing a reply; remaining
scripted turns are explicitly counted as skipped. Other scenarios start fresh.
Methodology and quality run independently, once per successful generated turn,
using the existing runtime functions and their unchanged prompts, validators and
bounded structural repair. Each evaluator has at most two attempts; no semantic
retry or user-response regeneration occurs. Evaluation failure does not block the
other evaluator or later generation. SDK transport retries retain SDK defaults;
no new application-level generator retry is introduced.

## Offline plan and explicit DEV live mode

```sh
python3 tests/run_dev_conversation_benchmark.py
python3 tests/run_dev_conversation_benchmark.py --dry-run --scenario-id repeated_uncertainty --max-scenarios 1
```

Default is dry run: validates synthetic input/configuration/local prompt sources,
with zero network, credential lookups, SDK client construction, DB/Telegram/FSM
access, and artifact writes. It does not pretend to generate conversations.
Neither the runner nor benchmark modules import bot, handlers, database, aiogram
or Telegram ports. Telegram is bypassed to avoid manual turn delivery and FSM
reset ambiguity; this benchmark uses no database persistence or user identities.

An explicitly authorized DEV live example (not executed during implementation):

```sh
python3 tests/run_dev_conversation_benchmark.py --live --model z-ai/glm-5.2 --base-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_API_KEY
```

Live requires all four explicit selectors: --live, --model, --base-url,
--api-key-env. The existing fail-closed DEV runtime guard must accept
`/opt/olga-coaching-dev` or its validated DEV container provenance before any
credential lookup or provider call. No env file is loaded/edited. Generator
credentials come from the named process environment variable; the unchanged
observer adapters require existing OPENROUTER_API_KEY separately. No keys are
printed or persisted. AsyncOpenAI is imported/constructed only after live gating.
A container invocation may use its validated `/app` worktree context.

Other options: repeatable --scenario-id, --max-scenarios,
--generator-max-tokens (default 350), --timeout (generator timeout, default 60),
--methodology-model, --quality-model, --evaluator-base-url.
Both evaluators default to the qualified z-ai/glm-5.2 baseline, max_tokens=4000,
low reasoning effort, timeout=60 and https://openrouter.ai/api/v1. Methodology
retains its reasoning object; quality retains reasoning_effort. Overrides are
explicit and recorded. Benchmark authorization enables the two direct evaluator
calls for this run; it does not read/change runtime shadow enable flags or their
configuration, and never creates dispatchers or capacity drops. Changing the
generator base URL does not silently change evaluator destinations.

## Artifacts and descriptive metrics

Live writes one exclusive JSON file below
`artifacts/evaluation/conversation-benchmark/`. It contains synthetic-only marker,
scenario IDs, model/config metadata without credential selectors or headers,
source/scenario fingerprints, timestamps, correlation hashes, input/output hashes,
per-turn generator status/latency and safe evaluator score/flag/label/validity/retry
projections. Only raw values in ephemeral memory reach model requests. No raw
user/candidate/history, reasons, evidence, provider envelopes, reasoning,
credentials, headers or environment containers are persisted. The writer rejects
unknown report/record/metadata fields and validates typed projections; metrics are
recomputed before writing. It refuses dry-run reports and redirected directories.
Existing runtime log events are also aggregate-only; raw returned methodology
results/attempts are deliberately discarded by the benchmark.

Reliability reports attempted, first/final valid, retries/recovery and failures.
Methodology reports hard fails, HF frequencies, overall and decision frequencies.
Quality reports overall frequencies, dimension 0/1/2/null distributions, flag
frequencies, weak progression/non_repetition/question_quality turns, Q03 scenarios
and consecutive adjacent-turn pairs, and scenarios with repeated low scores.
Semantic counts use final-valid evaluations only. Hard-fail rate uses final-valid
methodology evaluations. Invalid/missing evaluations are explicit reliability
failures and never interpreted as semantic passes. Null scores have their own
category, excluded from <=1 counts. Zero denominators return null.

Late deterioration compares mean ordinal quality in early vs late scripted halves
(strong=2, acceptable=1, weak=0; insufficient_context excluded). No eligible turns
in either half yields null. Counts of eligible turns are reported. A separate
first/last indicator requires a complete scenario and valid comparable endpoints.
These ordinal indicators are descriptive, not rubric revisions or routing scores.
Consecutive Q03 requires adjacent original turn numbers; missing/failed turns do
not bridge an apparent sequence.

Weakness analysis reports each dimension<=1 and each flag as a separate signal:
one occurrence within a scenario is isolated there; >=2 is repeated within that
scenario; presence in >=2 scenarios is cross-scenario recurring. These categories
can overlap and describe evaluator output only. No binary systematic verdict.
Latencies include failed attempts and report mean, median and nearest-rank p95
(ceil(0.95*n)); empty samples return null statistics.

For before/after comparisons, keep scenario IDs/order, synthetic first name,
model/settings and evaluator specifications fixed. Compare metadata fingerprints,
structural reliability and descriptive per-scenario/aggregate changes. Repeat runs
to characterize model variability; a single difference is not causal proof. Any
future generator change requires separate authorization. Raw conversation hashes
are correlation aids, not semantic repetition evidence.
