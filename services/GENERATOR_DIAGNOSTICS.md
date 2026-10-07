# DEV generator boundary diagnostics

The benchmark reports `empty_response` exactly when extraction returns `None`,
`""`, or a string whose `strip()` is empty. Zero choices or a missing message/content
field raises the original extraction exception instead. The generator does not
inspect finish reason, usage, reasoning, refusal or tool calls to choose content.
Historical benchmark artifacts discarded these fields, so the past four empty
responses cannot be causally diagnosed from those artifacts alone.

`generate_candidate(..., diagnostic_observer=...)` optionally emits a closed scalar
projection once per shared generator invocation, including exceptions. Without an
observer it emits nothing. Observer or metadata failures are contained; return
identity, extraction exceptions and provider exception identity are preserved.
No retry, alternate content extraction or reasoning-to-answer substitution occurs.
The request, headers, model selection and default 350 token budget are unchanged.
Existing SDK retry behavior is unchanged; diagnostics describe SDK invocations,
not every underlying HTTP exchange.

Safe fields: provider call success; choice count/selected positional index; allowed
finish reason; content field presence, static Python type, character length and
whitespace status; presence/character lengths of reasoning, reasoning_content and
reasoning_details text; refusal/tool-call presence and tool-call count; numeric
usage and reasoning-token usage; model match and known matching response model;
safe error category; exception HTTP status if available; latency and fixed signal
IDs. Different response models use `other_model`, avoiding arbitrary provider text.
Presence distinguishes an absent content field from an explicitly null value.
Zero-length content counts as whitespace-only too; distinct signals separate them.
Structured reasoning lengths include available `text` items only; unknown shapes
have null length. Successful HTTP status is not available from ordinary parsed
completion objects; success means the SDK call returned, not proof of HTTP 200 or
provider-envelope correctness. SDK APIStatusError exposes status_code/response;
headers/body/request ID are never read or emitted.

The installed SDK's message schema permits extras, so provider reasoning fields
may exist even though not declared. Their presence is measured at runtime, never
assumed. Completion token details declare reasoning_tokens. No raw provider
object, prompt, conversation, content, reasoning, refusal, tool arguments,
headers or credentials are serialized. The diagnostic CLI prints safe JSON only,
writes no artifacts, and makes no evaluator, database or Telegram calls.

Dry-run (default, no credentials/network/writes):

```sh
python3 tests/run_dev_generator_diagnostic.py --scenario-id work_and_autonomy
```

An explicitly authorized future live run, under the existing fail-closed DEV guard:

```sh
docker exec -w /app olga_bot_container_dev \
  python tests/run_dev_generator_diagnostic.py \
  --live --scenario-id work_and_autonomy \
  --model z-ai/glm-5.2 --base-url https://openrouter.ai/api/v1 \
  --api-key-env OPENROUTER_API_KEY --timeout 60
```

Exactly one synthetic scenario starts with empty history and uses the shared
system instruction/history/generator path. It stops at the first generator
failure without a scenario/turn retry. Metadata is observational, not a routing
or regeneration instruction. Candidate A, evaluators and benchmark rules remain
unchanged. No live diagnostic was run during implementation.


Default invocation without arguments is an offline plan for work_and_autonomy.
LIVE still requires an explicit scenario ID and provider settings; no live
scenario selection is implicit. Default invocation never reads credentials,
creates a client, or writes an artifact.
