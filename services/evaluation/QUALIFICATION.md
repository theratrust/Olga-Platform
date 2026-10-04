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
0 and max_tokens is 4096. The timeout is a transport/socket timeout, not a strict
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
the run continues, writes a report, and exits nonzero. Contract-valid semantic
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
