# Accepted incomplete coaching generations: frozen DEV analysis

Status: analysis only, 11 October 2026. No live calls, runtime change, prompt change, token-budget change, database access, or evaluator run. Scope is /opt/olga-coaching-dev on feature/method-core. The frozen run is artifacts/evaluation/multiturn-coaching-flow/20261011T_multiturn_frozen_01/.

## Evidence and the three outputs

The manifest records z-ai/glm-5.2, max_tokens=350, 66 accepted assistant turns, 72 generator calls, six retries, zero evaluator calls, and no DEV DB or Telegram use. All six conversation JSON files parse and are complete at file level. The manual review marks the following accepted nonempty texts as QUALITY_FAILURE. Lengths are Python character counts of the stored assistant string, including newlines.

| Scenario | Turn | Characters | Approximate ending | Structural observation |
|---|---:|---:|---|---|
| identity_after_relocation | 6 | 187 | “появляется или,” | Ends after conjunction “или” plus comma, inside an unfinished question clause; no terminal punctuation. |
| identity_after_relocation | 8 | 201 | “Что ты ещё замечаешь,” | Ends after a comma suggesting continuation of an opening question; no terminal punctuation. |
| rich_reflection_question_discipline | 10 | 331 | “что ты замечаешь” | Ends inside an opening question without terminal punctuation; no unmatched quote, list, or bracket. |

The common observable shape is a response cut off during a question. The exact lexical ending differs. Two comma endings are particularly strong structural signals; lack of a final question mark alone is weaker because short, intentional fragments can be valid. None ends inside a quotation, bracket, or list. This is not file truncation: the stored JSON is parseable and includes later transcript fields. The returned text was nonempty, so the harness recorded it as accepted.

## Provider response metadata and evidence limit

The runtime client is openai.AsyncOpenAI configured with the OpenRouter-compatible base URL in bot.py; the frozen runner creates an AsyncOpenAI client against the same URL. services/coaching_generator.py calls chat.completions.create with model, messages, max_tokens=350, and the two existing headers. It returns only response.choices[0].message.content. It neither checks choice.finish_reason nor retains the response object for the caller.

The existing optional services/generator_diagnostics.py projection demonstrates that the code can read choice.finish_reason when supplied. It recognizes stop, length, tool_calls, content_filter, and function_call, and reads numeric usage.completion_tokens when supplied. It also records safe error category, HTTP status from an exception when present, content type, and character length. The observer is opt-in and was not supplied by this runner or handlers/chat.py. Its result cannot affect acceptance. It does not currently project native_finish_reason or stop_reason. The separately implemented evaluator qualification adapter reads native_finish_reason from raw JSON and treats length as truncation, but that is a different client path and is not proof that this generator's parsed response exposed that field.

Thus finish_reason and usage are conditionally available to the shared generator before extraction, but their values for these 72 calls are unknown. Actual OpenRouter responses from this run were not stored. No stop_reason, native_finish_reason, completion-token count, successful HTTP status, or provider error envelope was captured in the manifest or turn attempts. The SDK's own transport retries, if any, are outside the runner's recorded generator-call count. The six saved retries contain only status, ValueError kind, and time; none has diagnostic metadata.

The 187, 201, and 331 character lengths do not establish completion-token counts. The 350 request cap may include non-visible generation or provider-specific accounting, but this run provides no token usage or finish reason. Classification of the cause is **D: insufficient evidence**. Explicit length termination is plausible; premature provider/model stop is also plausible. Application suffix parsing loss is not suggested by the code: the generator returns message.content directly and the saved JSON is intact. It cannot be excluded solely from these artifacts.

## Exact acceptance and delivery paths

1. Normal chat admits and persists the user message before generation, then reads the latest 20 messages and optional carry-forward ledger. It sends an acknowledgement before calling the generator.
2. The shared generator makes one application-level call and directly extracts message.content. Zero choices/missing fields raise; a null, blank, non-text, or nonempty partial content can return without generator-level validation. The optional diagnostic observer only observes.
3. handlers/chat.py has **no application-level retry**. Any exception in its generation/delivery block leads to the existing generic communication-error reply. There is no explicit empty/non-text check before delivery. A nonempty incomplete string proceeds immediately after an active-conversation check.
4. In the currently configured DEV direct-chat branch (DEV_DIRECT_CHAT=true in .env.dev at inspection), the candidate is sent to the user first and then inserted as an assistant history row. Thus an incomplete nonempty reply could be sent and stored. If send succeeds and the subsequent save fails, delivery and history can diverge; that existing ordering is outside this analysis.
5. In the moderated branch, the candidate is stored as a pending draft before admin notification. Approval checks only that the draft is nonempty text, then sends it and saves the approved assistant message. Thus an incomplete nonempty draft could also reach a user if approved. The current PROD route/configuration was not inspected; no PROD incidence claim is made.

The artifact-only harness uses the **same shared generator extraction function and 350 cap**, plus current history and carry-forward assembly, but a **simplified, separate acceptance layer**. Its runner checks that the returned value is a nonblank string, raises ValueError otherwise, and tries at most three times for any caught exception (two retries) before abandoning the scenario. It records an accepted reply in local history only after this check. Runtime has no corresponding two-retry policy. Therefore three of 66 is a frozen-harness observation, not a measured Telegram runtime rate. The shared blind spot is that a nonempty partial string is not judged complete.

### Why the six retries occurred

| Scenario/turn | Attempts | Saved error kinds | What can be concluded |
|---|---:|---|---|
| rich_reflection_question_discipline T10 | 3 | ValueError, ValueError, then accepted text | Two failed attempts; third is one of the incomplete outputs. |
| answered_question_continuity T6 | 3 | ValueError, ValueError, then accepted text | Two failed attempts. |
| answered_question_continuity T7 | 3 | ValueError, ValueError, then accepted text | Two failed attempts. |

The runner itself raises ValueError for empty, whitespace-only, or non-string output, but also catches propagated exceptions from the client/generator and stores only the exception class. These six ValueErrors therefore cannot be conclusively separated into empty output, non-text output, or a propagated ValueError. They are **not** evidence of six provider errors, nor is there evidence of useful finish/token metadata on the attempts. No technical retry preceded identity T6 or T8.

## Detection and recovery options

| Option | Assessment |
|---|---|
| A. Provider finish-reason check | Preferred first guard for an explicit choice.finish_reason == length. The shared generator sees this field if the SDK supplies it; existing fake-response diagnostics and the independent evaluator adapter already recognize length. It is deterministic and low false-positive. It cannot explain or necessarily catch these three without their missing metadata. Treat unknown/missing metadata as unknown, not stop. Do not assume native_finish_reason or stop_reason are exposed by this parsed path. |
| B. Structural incomplete-text heuristic | The two conjunction/comma endings are strong examples, but Russian fragments, quotations, and stylistic pauses create false positives. A generic terminal-punctuation requirement would reject valid coaching replies. Any future heuristic should be extremely narrow and separately qualified against real complete fragments. It is not the first implementation slice. |
| C. One retry on explicit truncation | One extra call only for a positive length signal, with identical trusted system instruction, history, model, and max_tokens=350. The replacement is the complete second result; do not concatenate or persist the first. Acceptance must occur before direct send or draft creation to avoid duplicate assistant rows. A second explicit truncation must not trigger an unbounded loop. |
| D. Fallback after failed retry | Sending either incomplete attempt knowingly risks a broken coaching reply; choosing the longer one is not evidence of completeness. The existing generic communication-error path with no assistant answer/draft is the safer current-behavior-compatible fallback. The user turn remains admitted, and the user can try again. Delivery/persistence ordering still needs an offline test. |
| E. Increase max_tokens | Not justified now. The cap is 350, but the run lacks finish reason and completion-token counts. Raising it could alter cost, length, tone, and pacing without isolating the cause. Keep 350 in the first slice. |

## Recommendation and first implementation slice

**A. PROVIDER-METADATA FIX JUSTIFIED**, narrowly: provider-declared length is sufficient evidence to prevent a future explicitly truncated response from being accepted, even though the cause of these three historical outputs remains unknown. This recommendation does not claim that all three would have been caught.

The smallest future slice is a typed incomplete-generation signal at the shared generator boundary when the first choice explicitly reports finish_reason=length, before returning content. Keep the existing content extraction, prompt, model, and 350 cap. In the normal chat caller, allow one retry **only** for that explicit signal, using the identical request; if the retry also fails or is explicitly truncated, use the existing generic failure route and create no assistant message or moderation draft. Other provider exceptions retain current application-level behavior. Evaluation runners may apply their own bounded policies around the same signal. Do not add a broad text-shape rejection or rely on unverified native fields in this slice.

## Minimal observability

Reuse the existing privacy-preserving scalar diagnostic pattern rather than retaining provider objects or coaching text. Per application attempt, record attempt number, whether content was empty/nonempty, allowed finish_reason or unavailable, content character length, completion-token count if supplied, fixed retry reason, and safe error category/HTTP status if present. Keep model/request identity and max_tokens in run metadata. Do not log prompts, raw user/assistant text, reasoning, provider bodies, credentials, or free-form error messages. If native_finish_reason is later needed, confirm its actual parsed SDK location and sanitize to a fixed allowlist first. Record SDK versus application retry counts separately when possible.

## Offline test plan (no tests added in this task)

1. Complete text with stop is accepted; one generator call.
2. Empty content exercises the existing caller-specific behavior: harness retry; runtime generic failure unless policy is separately changed.
3. Provider exception retains current runtime generic failure and existing harness catch/retry behavior.
4. Explicit finish_reason=length is detected even with nonempty text, if supplied on the parsed choice.
5. Explicit finish_reason=stop is accepted.
6. A truncated nonempty response cannot be sent or persisted when the provider reports length.
7. A structurally odd but valid short reply is accepted.
8. A valid reply without a final period is accepted.
9. An unmatched quotation is assessed as a possible future heuristic case, not automatically rejected by the metadata-only guard.
10. An unfinished conjunction with stop/unknown metadata documents the guard's false-negative boundary; with length it is rejected.
11. A length-flagged first attempt followed by a complete second attempt yields only the second response.
12. A length-flagged retry that also fails yields the generic failure and no assistant output.
13. Persistence/draft creation occurs only for the accepted final response.
14. Exactly one assistant history entry is created; no duplicate send or draft.
15. The request retains max_tokens=350 on every attempt.
16. Normal complete output incurs no extra LLM call.

Cover both DEV direct-chat and moderated branches with fake client/bot/DB ports. The existing tests already cover exact 350-token request/extraction, safe diagnostic projection, benchmark empty/non-text/provider-error handling, and session/approval fences; they do not cover a nonempty length-terminated coaching reply at the shared generator or handler boundary.

## Five risks

1. Text heuristics falsely retry valid Russian fragments and increase latency.
2. Broad retry rules unexpectedly double calls and costs; SDK-level retries may also occur separately.
3. Retrying after send or draft creation could duplicate Telegram delivery or assistant history.
4. Assuming OpenRouter/native finish fields beyond the parsed SDK choice could silently miss truncation or misclassify it.
5. A length guard may mask a budget issue if 350 is actually insufficient; preserve per-attempt metadata before considering a cap change.

## Multi-turn harness carry-forward

The recovered trajectory verdict remains **SINGLE-TURN QUALITY IS GOOD BUT MULTI-TURN COHERENCE IS WEAK**. Repeated reflect→question behavior remains a separate known defect. The prior narrow prompt fix was regressive; no prompt experiment belongs in this analysis. The harness document, six-scenario fixture, and fixture test remain untracked and untouched.
