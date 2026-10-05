# Response quality model qualification

This harness evaluates **derived product-quality criteria** against the frozen
22-case synthetic response-quality corpus. It does not qualify Olga methodology
compliance. The methodology evaluator remains separate. No quality score can
compensate for a methodology hard fail. This harness is for model selection only;
there is no runtime integration or change to Telegram, generation or shadow behavior.

## Offline default and explicit live mode

Run from `/opt/olga-coaching-dev`:

```sh
python3 tests/run_quality_model_qualification.py
python3 tests/run_quality_model_qualification.py --dry-run --model candidate --base-url https://provider.example/v1 --max-cases 2
```

Dry run validates the corpus/configuration and builds prompts with zero network
calls, no credential lookup and no artifact writes. Live mode requires explicit
`--live`, `--model`, `--base-url` and a nonempty credential in `--api-key-env`
(default `OPENAI_API_KEY`). No credentials are read at import or construction.
Other options: `--timeout`, `--max-tokens` / `--max-output-tokens`,
`--reasoning-effort`, repeated `--case-id`, and `--max-cases`.
Token aliases send the OpenAI-compatible `max_tokens` parameter; reasoning effort
sends `reasoning_effort`. Provider support must be checked separately before a live run.

The quality namespace reuses only generic transport, JSON parsing and sanitization
utilities from `services/model_qualification_adapter.py`, a neutral copy of the stable
transport implementation. The original methodology adapter is unchanged. No methodology contract, gold interpretation,
repair logic or metric semantics are imported. A full JSON fence is accepted by the
shared parser; no fields, evidence, labels, scores, nulls or schema are normalized.
Every parsed result passes the canonical quality contract before comparison.

## Outcome precedence

1. `INFRA_FAIL`: no validated final result after at most two attempts.
2. `QUALITY_SEMANTIC_MISMATCH`: overall_quality differs.
3. `OVERALL_MATCH_SCORE_AND_FLAG_VARIANCE`: overall matches, scores and flag set differ.
4. `OVERALL_MATCH_SCORE_VARIANCE`: overall matches, scores differ, flags match.
5. `OVERALL_MATCH_FLAG_VARIANCE`: overall and all six scores match, flag set differs.
6. `EXACT_MATCH`: complete validated result equals gold, including strings/list order.
7. `QUALITY_MATCH_DETAIL_VARIANCE`: overall, all scores and flag set match, but
   reason, anchored evidence wording, context detail or item ordering differs.

Comparison is between final validated results and synthetic quality gold only.
Infrastructure subtypes remain in attempt errors: transport_error, timeout,
http_error, provider_error, empty_response, truncated_response, response_format_error,
malformed_json and contract_invalid_output. HTTP 200 error envelopes are provider
failures. Provider length termination is truncation even when JSON looks complete.
Reasoning fields are diagnostics only, never evaluator results, and are excluded
from artifacts.

## Bounded structural repair

Maximum two attempts total. Retry only empty output, provider-declared truncation,
malformed JSON, missing/unknown fields, schema/type/flag-object shape errors,
duplicate list declarations, or repairable null/context declaration inconsistency.
The retry appends an allowlisted Russian technical diagnostic to the original prompt.
It includes neither prior output nor gold scores, flags, overall label or evidence.
No retry for valid semantic disagreement, score range/label errors, unknown flag IDs,
unknown dimensions, evidence disagreement, score/flag contradiction, overall/score
priority contradiction, provider/HTTP/timeout/transport failure. Structural validity
never implies the model judgment is correct.

## Metrics and artifacts

Report first-pass and final contract-valid counts/rates, infrastructure failures,
retry attempted/recovered counts and recovery rate. Separately report overall quality
agreement and a four-label confusion matrix; exact score agreement and 0/1/2/null
confusion matrices for all six dimensions; Q01–Q08 TP/FP/FN, precision and recall;
exact full-result agreement; all outcome counts; case latencies and total elapsed.
No aggregate binary qualification score is calculated.

Agreement rates use all attempted cases (infrastructure failure counts as
non-agreement). Confusion matrices and flag precision/recall use final valid cases
only; excluded counts are explicit. Matrix rows are gold and columns are predictions.
Null is a separate score category. No MAE is calculated. Zero denominators are null.

Live reports are exclusive JSON files under `artifacts/evaluation/quality/`, with
synthetic corpus inputs/gold, sanitized attempts/envelopes, final validated result,
model/configuration metadata and metrics. Writer verifies inputs/gold against the
canonical frozen corpus and rejects dry-run reports and redirected artifact paths.
Headers, environment containers, credentials and reasoning are removed/redacted;
URLs are reduced to hosts. Sanitization is bounded and uses the active key; it is
not a detector for arbitrary unknown secrets. Never run on real conversations.

Offline validation:

```sh
python3 -m pytest -q tests/test_quality_model_qualification.py tests/test_response_quality_evaluator.py tests/test_model_evaluator_qualification.py tests/test_coaching_evaluator_contract.py
python3 tests/run_response_quality_cases.py
python3 tests/run_coaching_evaluator_cases.py
git diff --check
```
