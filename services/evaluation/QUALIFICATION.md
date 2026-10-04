# Offline evaluator qualification

This infrastructure compares declared evaluator-model results with the unchanged
22-case synthetic corpus. It never changes live coaching responses or routing.
The existing contract remains the only structural validator.

Default execution and --dry-run build all selected prompts without constructing
an HTTP request, reading credentials, or writing reports:

```sh
python3 -B tests/run_model_evaluator_qualification.py --dry-run \
  --model qualification-candidate --base-url http://127.0.0.1:9999/v1
```

--case-id can be repeated. Selection retains corpus order; --max-cases applies
following selection. Unknown/duplicate IDs and nonpositive limits are errors.

Live runs require explicit --live and an API key supplied only through the named
--api-key-env variable (default OPENROUTER_API_KEY). No live run is authorized by
this document. The adapter accepts HTTPS, or HTTP on localhost only. Redirects
are disabled; there is no provider fallback, automatic retry, or LiteLLM import.
The base URL is explicit and receives a /chat/completions suffix. Temperature is
0 and max_tokens defaults to 2500. The timeout is a transport/socket timeout, not a strict
whole-run deadline. Sequential processing retains corpus ordering.

Reports use exclusive UTC timestamp/model/hash/random filenames beneath
artifacts/evaluation/. They contain metadata, synthetic inputs, sanitized HTTP and model
output, parsed/validated/expected results, structured errors, mismatches, latency,
and separate metrics. Credentials are omitted from metadata and redacted from
artifact strings, including JSON-escaped copies of the configured credential.
Header/authorization and environment containers are dropped. Recognizable bearer
credentials, key/password assignments, and environment assignments are redacted;
URLs are reduced to safe host references without userinfo, path, query, or fragment.
Provider errors are sanitized at adapter capture and artifacts are sanitized again
before writing. JSON debug envelopes are decoded/re-serialized during sanitization;
they are not byte-identical wire transcripts. Excessively nested data is replaced
with a redaction marker. Sanitization does not modify caller-owned objects.
Diagnostics never print raw response bodies, headers, or transport exceptions.
The sanitizer knows the configured key and recognizable credential patterns, not
arbitrary unknown private values; this tool accepts only the fixed synthetic corpus.
Raw request headers and environment dictionaries are never captured by the harness.
Raw artifacts remain model-generated debugging data; they are not method authority.

All agreement/full-result rates use attempted cases; invalid responses count as
nonagreement. HF precision/recall and per-rule TP/FP/FN use contract-valid cases
only, with explicit excluded counts. Undefined precision/recall is null. Full-result
match compares normalized JSON objects, including exact rationale strings and
array order; it is a strict diagnostic rather than a semantic-quality threshold.
No single aggregate acceptance score or automatic model approval is defined.

Adapter, malformed JSON, and contract-invalid results are infrastructure failures:
the run continues, writes a report, and exits nonzero if infrastructure failure
persists after any eligible structural retry. Contract-valid semantic
mismatches are reported and do not cause an infrastructure failure exit code.
Dry-run success demonstrates prompt/configuration readiness, not provider readiness
or model qualification. Pytest uses mocked transports and results only.

## Provider/protocol failures and timing

Failures distinguish transport timeout (`timeout`), transport error, HTTP error,
HTTP-200 provider error envelope (`provider_error`), empty response, malformed
protocol envelope, malformed evaluator JSON, and contract-invalid evaluator result.
A provider envelope with error/errors, success=false, status=error/failed/failure,
or type=error is checked before model content extraction, even if choices exists.
Such an envelope never reaches evaluator JSON parsing or contract validation.
Safe evidence includes HTTP status, scalar provider type/code, sanitized message,
model name, backend host, and latency. HTTP error bodies are read with the same
1 MiB bound as success bodies, then sanitized; headers are not retained. Later
cases continue after handled failures. Contract-valid semantic mismatches have
an explicit outcome separate from infrastructure errors.

insufficient_context agreement compares only the present flag; individual missing
items are checked only by the full-result comparison. Per-case latency starts
immediately before adapter dispatch and ends after parsing, contract validation,
and comparison/error handling. Total elapsed time covers the qualification loop,
including prompt building and expected-result validation, but excludes initial CLI
setup, metric aggregation, report sanitization, and artifact writing. Transport
failures and invalid results remain in attempted-case denominators and are excluded
from HF TP/FP/FN. Zero predicted positives makes precision null; zero expected
positives makes recall null. A zero numerator with a positive denominator is 0.

## Reasoning-model truncation and qualification controls

Only message.content is an evaluator output. message.reasoning, reasoning_content,
and reasoning_details are never parsed as candidate JSON and are removed from
persisted debug envelopes; only a reasoning_present Boolean is retained.
An HTTP-success response with finish_reason=length or native_finish_reason=length
is truncated_response regardless of content: null, empty, whitespace, partial JSON
or apparently complete JSON. Provider-declared length termination makes output
completeness untrustworthy. Content never enters evaluator parsing or contract
validation; sanitized content is retained only in the debug envelope. Without a
length marker, missing output remains empty_response and nonempty content remains
subject to strict JSON parsing and contract validation. Safe completion
metadata records HTTP status, finish_reason, optional native_finish_reason, model,
provider/backend host and reasoning presence. Latency remains on the case record.

--max-tokens (alias --max-output-tokens) defaults to 2500. ModelConfig may omit
max_tokens by setting it to None. Optional reasoning fields are omitted by default,
so unsupported parameters are never silently added. The output cap is the default
bound; provider-specific accounting may include reasoning in that cap and does not
guarantee visible output. For a supported route, explicitly choose low effort or a
bounded budget:

- --reasoning-effort low with --reasoning-format reasoning (default shape) sends
  reasoning={"effort":"low"}.
- --reasoning-effort low --reasoning-format reasoning_effort sends the distinct
  top-level reasoning_effort="low" shape.
- --reasoning-budget 512 sends reasoning={"max_tokens":512}.
- --reasoning-json '{"effort":"low","max_tokens":512}' passes an explicitly
  configured JSON object for the reasoning shape. Budget/JSON flags require that
  shape; no provider compatibility is inferred.

The reasoning flags are mutually exclusive. Invalid limits and conflicting shapes
fail before dispatch. Generation settings are included in qualification metadata
under reasoning_config/reasoning_effort_config, separately from discarded model
reasoning text. These options affect this harness only, never live coaching or
runtime routing. Changing provider/model still requires explicit live authorization.


## Qualification outcomes (report version 1.2)

Each case has exactly one outcome:

- EXACT_MATCH: contract valid and the normalized full result equals expected.
- SEMANTIC_PASS_DETAIL_VARIANCE: contract valid; hard_fail, overall, decision,
  HF rule set and insufficient_context.present all match, but full equality does
  not. Rationale, source references, contract-valid scores and list ordering can
  vary without changing these labels.
- SEMANTIC_MISMATCH: a contract-valid result differs in one or more of those
  semantic labels.
- INFRA_FAIL: transport/provider, empty/truncated response, parsing or contract
  failure. The specific subtype remains in error.kind; no semantic comparison is
  performed on an invalid result.

Console and report metrics separate infrastructure_failures,
semantic_label_mismatches, semantic_pass_detail_variance and exact_matches.
These mutually exclusive counts sum to attempted cases. The existing
semantic_label_mismatch_cases metric is retained as an alias count. Agreement
rates, exact full-result match rate, HF precision/recall, denominators and latency
semantics remain unchanged. Detail variance is not full equality or automatic
model qualification. Scores still must satisfy the canonical contract.


## Bounded structural recovery (report version 1.3)

Qualification enables one output-format retry by default (maximum two dispatches
per case). --no-structural-retry disables recovery for a first-pass-only run.
Eligible failures are truncated_response, empty_response, malformed_model_json,
and contract-invalid structural/schema errors recognized by a conservative
allowlist of shape, required/unknown fields, types, nonempty values and enums.
Excerpt failures, unsafe paths and decision-priority inconsistencies are not
eligible. Reference eligibility is refined below in report version 1.4. Transport, timeout, HTTP and provider errors have no added retry policy.
Valid judgments, semantic mismatch and detail variance are never retry triggers.

Retry sends the original evaluator prompt and synthetic input plus a Russian
format-only correction. For structural contract failures it adds a static, sanitized
schema diagnostic; raw validator exceptions, previous output/reasoning and gold
results are never supplied. The retry does not change generation parameters.
There are no recursive retries. A failed second attempt remains INFRA_FAIL.

Each case preserves first_attempt and optional retry_attempt, each with sanitized
evidence, outcome/error, parsed/validated results and dispatch-to-validation
latency. attempt_count, recovered and final_selected_result are explicit. Existing
top-level result fields select the final attempt. Case latency sums attempt
latencies; total elapsed includes retry preparation. Recovered console outcomes
are prefixed RECOVERED_ and retain the actual final comparison category.

Metrics add first_pass_contract_valid_cases, first_pass_contract_valid_rate,
first_pass_infrastructure_failures; retry_attempted_cases, retry_recovered_cases,
retry_recovery_rate; final_contract_valid_cases, final_contract_valid_rate,
final_infrastructure_failures. First/final rates use cases as denominator; recovery
rate uses retried cases and is null when no retry occurs. Recovery means contract
validity, regardless of semantic agreement. Existing agreement/HF/full-result
metrics use final selected results, keep their case denominators and exclusions,
and do not count retries as additional corpus cases. First-attempt failures remain
visible even after recovery. Dry-run remains network-free and writes no artifacts.


## Safe contract diagnostics and deterministic repair (report version 1.4)

Every candidate-result ContractError records contract_error_kind and contract_error,
plus structural_retry_eligible. Diagnostics retain trusted field locations and fixed
safe descriptions, never raw filesystem exception text, supplied field values,
headers, environment data or derived expected decisions. Active-key redaction still
applies to both attempts and final artifacts. Unknown failures use other_contract_error.

The classifications are schema_shape_error, invalid_source_path,
invalid_source_heading, source_reference_inclusion_error, null_score_without_context,
missing_required_field, unknown_field, decision_priority_error,
excerpt_evidence_error and other_contract_error.

One retry is allowed for schema shape, exact source heading, source-reference
inclusion, null-score/context, missing-field and unknown-field errors. A source path
is retryable only for canonical spelling/reference-generation errors or missing
files with lexically contained knowledge/method/ paths. Absolute paths, traversal,
NUL, backslashes, symlink containment failures, filesystem/permission failures and
unknown path errors are not retryable. Unknown HF identifiers, excerpt errors and
decision-priority errors do not trigger repair. The original output failure allowlist
(truncated_response, malformed_model_json, empty_response) remains unchanged;
transport/provider errors and valid semantic differences never trigger retries.

The Russian repair prompt contains only the original evaluator input and the safe
technical diagnostic, without gold results. Source headings, е/ё and provenance
are never normalized or repaired by the harness; the model must return valid exact
references. The canonical validator is unchanged: null scores require present=true
and missing context items. Both attempts, first-pass reliability, final semantic
metrics and the maximum of two attempts remain as documented above.
