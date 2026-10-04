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
candidate SHA-256, hashed existing session ID, hard_fail, violation rule IDs, scores,
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
