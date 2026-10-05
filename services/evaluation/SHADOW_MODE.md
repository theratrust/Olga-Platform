# DEV methodology evaluator shadow mode

Shadow evaluation observes candidates using z-ai/glm-5.2; it neither approves a
model nor executes a route. The candidate is sent through the existing direct-chat
or moderation delivery path before scheduling observation. accept, retry, escalate
and insufficient_context are logged projections only. No regeneration, rewriting,
suppression or evaluator wait precedes delivery. The optional hook is isolated from
the generator and all failures are fail-open.

Disabled by default. No env file is changed by this implementation. There is no
existing environment example; this document is the configuration reference:

- EVALUATOR_SHADOW_ENABLED=false (only explicit true enables observation)
- EVALUATOR_MODEL=z-ai/glm-5.2
- EVALUATOR_MAX_TOKENS=4000
- EVALUATOR_REASONING_EFFORT=low (OpenRouter reasoning effort object)
- EVALUATOR_TIMEOUT_SECONDS=60 (per provider attempt)
- EVALUATOR_BASE_URL=https://openrouter.ai/api/v1 (optional evaluator endpoint)
- OPENROUTER_API_KEY comes only from the existing process environment.

Do not enable without separate authorization. To disable, set
EVALUATOR_SHADOW_ENABLED=false in the DEV process environment; the dispatcher reads
it for each new submission. In-process shadow_dispatcher.disable() immediately
stops new observations without restarting the bot. Existing in-flight observations finish but cannot
execute routes. File environment changes require normal DEV process reload; this
module does not watch env files. Runtime identity uses the evaluator module's
repository root, not cwd. Host /opt/olga-coaching-dev is accepted. Container /app
requires both existing DB_NAME=dev_bot.db and exactly one /app entry in
/proc/self/mountinfo whose mount root is /opt/olga-coaching-dev. This was verified
read-only for olga_bot_container_dev. /app alone or DEV_DIRECT_CHAT alone is not
sufficient. Missing/unreadable/ambiguous mount evidence fails closed. Explicit
non-DEV APP_ENV/ENVIRONMENT/BOT_ENV/RUNTIME_ENV, an incompatible ENV_FILE or DB_NAME,
PROD paths and arbitrary roots are rejected. The guard does not access the Docker
socket, env files, database or network. No PROD files, environment or services change.

A dedicated single-thread worker supports at most one outstanding observation;
saturated submissions are dropped with a capacity failure record, without queueing.
Observer cancellation does not free a still-active worker slot. Shutdown drains
outstanding work. Per-attempt HTTP timeout follows the existing adapter semantics;
it is not a strict wall-clock deadline against a slow streaming peer. At most one
format repair is allowed, using the shared deterministic repair policy. Transport/
provider errors and nonrepairable evidence/priority errors are not retried. Missing
keys, unexpected exceptions, parsing/validation failure and logging failure cannot
alter user-facing delivery. No full raw provider response or reasoning is persisted.

The evaluator uses only the ordered history already supplied to the generator,
bounded to its existing 20-message limit, and no external memory. Current history
may contain the latest user turn, exactly as it does for the generator; no turns
are fabricated. Prompt/specification and canonical contract are reused unchanged.
The repair module has no gold corpus or qualification-metric dependency.

Structured log events: SHADOW_EVAL_OK, SHADOW_EVAL_RECOVERED, SHADOW_EVAL_FAIL.
Success/failure projection records include timestamp, mode=shadow, evaluator_model,
candidate SHA-256, hashed conversation-instance ID, hard_fail, violation rule IDs, scores,
overall, decision, shadow_route, insufficient_context present flag, first/final
contract validity, retry attempted/recovered, latency_ms, first-pass error kind
and safe final error kind.
Scheduling/capacity failures have minimal event/error records. Logs exclude raw
conversation, candidate text, rationale, violation excerpts, credentials, headers
and environment data. Hashes are correlation identifiers, not anonymization.
The service returns sanitized canonical results/attempt metadata to its caller;
those are not written into logs. No qualification outcome labels are emitted.
No route is executed yet. No live evaluator calls were made in implementation tests.


## Logger and scheduling visibility

Only services.evaluation.runtime explicitly sets its logger to INFO with
propagate=True. It installs no handler and leaves root and unrelated logger policy
unchanged. Events flow to the bot's existing output handler (normally stderr,
captured by Docker logs). If an operator explicitly configures an output handler
above INFO, that handler can still filter these records; this module does not
override handler filters or global logging configuration.

SHADOW_EVAL_SCHEDULED is emitted once after background-task acceptance, with
timestamp, mode, model and candidate/session hashes only. The existing final
SHADOW_EVAL_OK/SHADOW_EVAL_RECOVERED/SHADOW_EVAL_FAIL records are retained. Saturation
continues to produce SHADOW_EVAL_FAIL with capacity_exceeded, never a scheduled
event. Disabled shadow mode produces neither scheduling nor evaluation records.
Repeated imports do not add handlers or duplicate events. No raw evaluator output,
user text, headers or credential values are added to logs. Logger changes do not
change routes, enable/disable shadow mode or alter user delivery.


## Offline DEV shadow evidence report

From /opt/olga-coaching-dev, collect only the named DEV container's logs:

```sh
docker logs --timestamps olga_bot_container_dev 2>&1 | python3 -B scripts/report_shadow_evaluations.py
```

The reporter itself never runs Docker, imports the bot, calls a model or executes
routes. It accepts stdin by default (or -) and supports a supplied log file confined
to the DEV repository, including symlink containment checks:

```sh
python3 -B scripts/report_shadow_evaluations.py artifacts/evaluation/dev-shadow.log
python3 -B scripts/report_shadow_evaluations.py --json < artifacts/evaluation/dev-shadow.log
```

Only aggregate counters are printed. Raw log input, model names, hashes, conversation,
rationale, excerpts, provider payloads, credentials, headers and environment values
are never printed. Unknown error-kind strings are grouped as other_error rather
than echoed. The reporter retains safe enums/numbers/flags only; malformed/unrelated
lines are counted and ignored. Do not persist unfiltered Docker logs into Git;
stdin avoids creating a raw log copy.

Scheduled records count accepted work only. Completed records count terminal OK,
RECOVERED and evaluator FAIL events. capacity_exceeded and configuration_or_scheduling_error
are separate non-evaluation failures, not completions. Completion rate is completed /
scheduled, or null/n/a without schedules. A partial log window can yield a rate above
100%; it is not clamped or treated as evidence of successful matching to a schedule.

Route rates use final-contract-valid completed evaluations. Hard-fail rate uses final
valid records with an explicit Boolean hard_fail. Each HF ID counts at most once per
valid evaluation. Scores show 0/1/2/null frequencies for valid records; absent or
invalid score fields are excluded. First/final valid rates use completed records
with their corresponding explicit Boolean flag. Retry-attempt rate uses records
with that flag; recovery rate uses retried records with a recovery flag. Missing
flags are unknown and excluded, not counted as false. Denominators are included in
JSON output. Error frequencies include safe failures from both completed and dropped
work. Latency uses finite nonnegative terminal latency_ms values; p95 is nearest
rank (ceil(0.95*n)), with null/n/a for an empty set.

Deduplication uses event type, normalized timestamp and valid candidate/session
hashes, when present. Timestamp is required; missing hashes fall back to event/time.
Scheduled and terminal records are separate; identical candidates at different times
remain distinct. Deduplication applies within one input run: concatenating repeated
log captures does not double-count identical events. Without runtime attempt IDs,
conflicting records or separate events sharing the same identity cannot be resolved
by this observational reporter. It provides no methodology gold comparison,
qualification approval, assurance verdict or routing action.

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
