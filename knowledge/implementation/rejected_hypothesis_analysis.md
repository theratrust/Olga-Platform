# Rejected assistant hypotheses: runtime and method analysis

Status: architecture analysis only, 11 October 2026. No behavior, prompts, tests, evaluators, or schema changed. This report distinguishes source rules from proposed implementation choices. Static inspection and deterministic offline probes establish context behavior; they do **not** establish how a live generator will respond.

## Source authority and traceability

The project's [source-of-truth document](../method/источник_истины_метода_Ольги.md) reports **no independently verifiable primary Olga interview or real conversation** in the repository. The following are validated/project method rules, not independently authenticated Olga quotations.

| Rule | Relevance | Status of behavior proposed here |
| --- | --- | --- |
| O-M07 | Do not assign hidden feelings/motives or promote interpretation to fact. | Directly supported method boundary; rejecting a hypothesis never proves a hidden state. |
| O-M08 | A user-grounded, tentative hypothesis must be rejectable; do not contest rejection. | Directly supported method boundary; not defending/reasserting a rejected interpretation follows from it. |
| O-M04, O-M10 | Client authorship and priority of the client's own topic/words. | Directly supported boundary for following the correction and allowing the client to reopen an idea. |
| O-AI04, O-AI05 | Mark hypotheses and accept refusal without immediate replacement. | Necessary operationalization of O-M07–08. |
| O-AI09 | Use verifiable history/corrections, with current user wording first. | Existing **design choice** supporting the runtime ledger. |
| O-M06, O-AI03 | Do not fill «я не знаю» with candidate explanations. | Project method/product boundary; uncertainty is not rejection. |
| O-M11, O-AI06 | Do not automatically blame partner or prescribe work. | Derived thematic constraint in partner/work examples. |
| O-U04, O-U08 | Hidden motives are unsupported; ledger/window numbers are product choices. | Explicit limit on what the runtime may claim as method truth. |

`поведение_AI_бота.md` §§3,13 says to distinguish assistant hypotheses from user words, accept correction, never treat disagreement as confirmation, and return to what the client actually said. `карта_коучингового_разговора.md` §§5 and “Сквозные границы” makes the same derived distinction. A permanent topic ban, a semantic classifier, and the exact representation of a rejection are **design choices**, not direct statements by Olga. The user's later explicit position has priority.

## What counts as a hypothesis or rejection

1. **Assistant-originated interpretation** (“Возможно, тебе страшно потерять…”): a candidate for tracking only if the delivered assistant turn proposes a specific account and a later user turn explicitly rejects that account. It must not be stored as a fact.
2. **Assistant-originated causal account** (“Может быть, ты остаёшься потому что…”): same rule. A causal explanation is still an assistant hypothesis.
3. **Reflection of the user's own idea** (“Наверное, я боюсь остаться одна” originated with the user): do not label the idea an assistant invention. If the assistant adds a new meaning beyond that quote, only the added meaning can be a hypothesis.
4. **Neutral open question** (“Что для тебя сейчас самое важное?”): no hypothesis to reject. A subsequent “нет” may reject a request, not an interpretation.
5. **Candidate-option question** (“Это больше про страх или про усталость?”): conceptually proposes candidate states and may be rejected, but the current detector does not recognize it. Tracking requires proof that the user rejected a specific assistant-originated candidate; a generic no or answer to a different part is insufficient. Such questions also risk O-M07/O-AI03 independently.

Strong rejection may be “Нет, дело не в этом”, “Это не так”, “Я так не думаю”, “Нет, я не боюсь этого”, “Ты неправильно поняла”, or “Это вообще не про него” **when its referent is clear**. A bare “Нет” can be an immediate conversational rejection, but is unsafe as portable memory without a self-contained referent. “Не знаю”, “возможно”, silence, topic shift, partial qualification, weak disagreement, and rejection of advice/action are not automatically rejection of a psychological hypothesis. The last may be an explicit user boundary of a different type.

## Exact current path and failure modes

`handlers/chat.py` atomically saves the admitted user turn, reads `get_recent_history(user_id, conversation_id, limit=20)`, then reads all same-conversation rows through `get_conversation_history_with_ids(user_id, conversation_id)`. `database.py` returns the newest 20 in chronological order and the full source in increasing row-ID order. `build_carry_forward` in `services/conversation_state.py` verifies that the latest source rows exactly match the 20-message read; if not, memory is empty. This is a safe fail-closed snapshot check. Both queries are scoped by user and DB conversation ID. `/new` rotates the ID and removes previous rows. No separately stored state or extra model call exists.

The detector examines **user rows older than the visible 20-message window only**. For `rejected_assistant_hypothesis` it requires an immediately preceding persisted assistant row; an earlier user row (guard against a late assistant row after reset); a single-line, at-most-180-character quote with no internal sentence punctuation; an assistant quote beginning with a narrow marker (`возможно`, `может быть`, `можно предположить`, `может ли быть`, `могу предположить`, `как тебе [такая] гипотеза`); at most one question mark; an explicit rejection prefix (`нет, это не…`, `нет, я не…`, `нет, дело не в…`, `нет, не поэтому…`, `это предположение не…`, `эта гипотеза не…`); and at least one shared Cyrillic word of five or more letters after stop words. The stored item contains the rejection's source message ID, the preceding assistant message ID, event type, and the **exact short user quote**. It does not contain the hypothesis text or a semantic label for the idea.

`_superseded` omits a candidate if a later user quote begins with a narrow correction marker and shares a significant token. At most four latest distinct eligible older events survive **across both event types**; newer boundary events can crowd out a rejected-hypothesis event. Empty/malformed/mismatched history, excessive quote length, multi-sentence text, ambiguity, or inability to link content yields no ledger. This is deliberate false-negative preference.

`render_runtime_memory` adds a labeled Russian data block only when events exist. It says the quotes are earlier user words, not current words or psychological interpretation; the event means only explicit refusal; do not return to the rejected account without user initiative; current user wording/correction wins. `build_messages` appends the block to the existing **system message** before the chronological raw history. Recent rejection pairs get **no explicit rejection annotation**: the generator only sees the assistant/user turns and the general prompt/method-core instructions (`prompts/coaching.py` §4; `services/methods/loader.py` loads `границы.md`, but not `поведение_AI_бота.md` or the conversation map). There is no post-generation rejection guard. Voice transcripts use the chat handler; moderated drafts use the same generation assembly after user admission. Only delivered/persisted assistant rows can become ledger sources; an unapproved draft cannot.

Deterministic offline probe of current code: a recent hypothesis/rejection pair yielded `[]`; the same pair after 27 filler messages yielded one source-linked event; “Нет, я вообще не боюсь этого” after “тебе страшно потерять привычную жизнь?” yielded `[]` because the rejection and hypothesis share no qualifying word. A later “Хотя сейчас думаю: зависимость меня всё-таки пугает” did **not** remove an older rejection because it lacks the current correction prefixes. The current-message-priority instruction remains, but stale memory can still conflict with a genuine later reversal.

Thus the observed mechanism is **A+D+E**, with **B** where a stored quote does not identify the rejected proposition well. **F** contributes: general “do not persuade” guidance is present, but recent rejected pairs are not explicitly marked and the base prompt does not state a durable closure rule. **C is unverified** without live output; do not attribute a particular recurrence to model disregard. **G is not the primary runtime cause**: canonical examples and method evaluator generally reject pressure, but they cannot prevent a response. Paraphrasing (“страшно потерять привычную жизнь” → “пугает, что всё изменится”) is semantic recurrence; exact-token detection or response blocking cannot reliably prove equivalence.

## Invariants to preserve

- No rejection event from generic “нет” lacking a portable referent, “я не знаю”, uncertainty, silence, topic change, or a partial answer.
- No event without an identifiable **preceding delivered assistant hypothesis** and an explicit, linked user refusal. A neutral question or rejection of an action/request is not an interpretation refusal.
- No assistant wording promoted to a user fact. No inferred motive, diagnosis, resistance, or partner/work frame.
- Source IDs, exact user wording, bounded items, chronological/same-conversation checks, current-user priority, and empty-ledger inertness remain.
- When the pair is ambiguous, omit it. Do not widen lexical patterns merely to make benchmark examples pass.

Existing `tests/test_conversation_state.py` covers a carried linked refusal, ambiguous replies, unrelated “нет”, missing assistant hypothesis, bare refusal, “я не знаю”, current correction, recent-event nonduplication, snapshot mismatch, count bound, and session isolation. It does **not** prove consistent generator context for the same rejection before and after window expiry, semantic paraphrase prevention, or robust user reopening.

## Options

| Option | Potential benefit | Cost/risk | Assessment |
| --- | --- | --- | --- |
| A. Narrow prompt-only line | Explicitly tells generator that a rejected account is closed while user may reopen it. | Prior prompt-only attempts regressed conversations; cannot restore a rejection after it leaves history; extra global instruction applies even with no evidence. | Insufficient alone. Consider only after offline comparison shows runtime evidence still ignored. |
| B. Always surface conservative rejected-hypothesis events | Same source-linked rejection signal inside and outside the 20-message window; no new call, classifier, DB table, or history rewrite. | Repeats a short recent user quote in labeled runtime data; 4-item cap and false negatives remain; an outdated event must yield to later user words. | **Preferred first slice.** Keep older boundary/correction behavior and exact detector safeguards. |
| C. Annotate raw history | Places rejection beside the relevant turns. | Pollutes chronological dialogue, may elevate derived text to a speaker's words, increases tokens and message-assembly complexity. | Do not use in first slice. Never edit the actual user message. |
| D. Guard generated response | Could catch literal repetition after generation. | Paraphrases evade exact checks; broad keyword blocking suppresses legitimate user-authored discussion; delivery/retry policy becomes complex. Shadow evaluators currently run after delivery. | Do not use without strong offline precision evidence. |
| E. B plus one narrow instruction | Evidence plus explicit policy might improve compliance. | Prompt change can create new conversational regressions and is not needed to establish representation. | Conditional second step only if B alone fails offline qualitative qualification. |

**Recommended semantics (design choice):** expose at most the existing conservative, source-linked `rejected_assistant_hypothesis` event for the current conversation even when its pair is still in the raw 20. Keep boundary/correction carry-forward old-only; do not duplicate events already represented by an older ledger item. Label the block as runtime data and make clear that only the assistant's prior proposal was rejected. No ungrounded “topic closed” or psychological state label. Preserve the current system prompt and single raw history sequence. Before implementation, settle whether recent rejection slots can evict older boundaries under the four-item cap; a minimal cap/priority rule must not silently weaken existing old-boundary protection. Do not broaden the lexical detector in this first slice.

**User reopens an idea:** the assistant must not initiate its return, but the user may. A current explicit statement (“Хотя я сейчас подумала — одиночество меня всё-таки пугает”) overrides any memory, as the existing block says. For later turns, a future implementation needs a conservative same-idea reversal rule or must omit the old event when a clear source-linked user retraction is provable. The current `_superseded` token/prefix heuristic misses this example; it is unsafe to claim the problem solved by injection alone. When linkage is uncertain, retain the exact historical rejection only as historical data and obey the current user statement; never make a permanent prohibition. Test the precise reversal before claiming consistent behavior across turns.

## Synthetic dialogue and evaluator audit

`knowledge/method/примеры_коучинговых_разговоров.md` labels all examples synthetic. Dialogue 6, exchanges 3–5: assistant proposes a calendar-sequence hypothesis; user says she remembered the calendar; assistant accepts that the hypothesis does not fit, then follows her chosen focus. No later return to the rejected interpretation was found. Dialogue 2's refusal to seek work is a **user boundary**, not proof that an assistant psychological hypothesis was rejected. The examples model acceptance rather than persistence, but are not a live behavioral guarantee.

`knowledge/evaluation/метод_Ольги_оценка.md` HF08 specifies a **hard fail** for defending, proving, repeating as correct, or immediately replacing a rejected hypothesis with another characterization. `tests/coaching_evaluator_cases.json` includes accepted refusal, immediate replacement (HF08), explicit pressure (HF08), and missing-context cases. The evaluator prompt receives conversation context, user message, and candidate; missing history must be marked insufficient rather than guessed. In `handlers/chat.py` both method and quality shadow observers are invoked **after** the delivery/draft path, receive only the latest raw `history` (not the runtime ledger), and do not alter the candidate. Thus HF08 has a written hard-fail rule but cannot reliably judge an old rejection absent from observer context, nor is semantic paraphrase accuracy statically proven. The quality rubric's `progression`/`question_quality` could rate a new question favorably, but explicitly says quality cannot override method hard fails and does not gate output. Smallest conceptual evaluator follow-up: add contrastive offline cases with full rejection context, paraphrased reopening, and user-led reopening; if later qualified, pass relevant source-linked context to the shadow evaluator. No evaluator change is needed for the first runtime slice.

## Offline reproduction and acceptance matrix

Fixtures should inspect deterministic extraction **and exact assembled generator messages**, with no provider call. For candidate responses, use human-labeled offline method cases; a deterministic string guard cannot establish semantic equivalence.

| # | Case | Expected evidence/behavior |
| --- | --- | --- |
| 1 | Assistant-originated interpretation, explicit linked rejection | One event with both source IDs and exact user quote. |
| 2 | Later verbatim reopening by assistant | Method case is HF08 when rejection remains operative. |
| 3 | Paraphrased reopening of the same rejected account | Human-labeled HF08 case; extractor alone must not claim semantic detection. |
| 4 | Later explicit user-led reopening | Current user wording wins; old event cannot be treated as a permanent ban. |
| 5 | “Я не знаю” after hypothesis | No rejection event; hard uncertainty rule remains. |
| 6 | Generic “нет” after unrelated/neutral question | No event. |
| 7 | Linked rejection within latest 20 | Same clearly labeled rejection data visible to generator; raw history unchanged. |
| 8 | Same pair at messages 3/4, current turn 30 | Source-linked event survives outside latest 20, subject to cap; no raw pair in window. |
| 9 | Two distinct hypotheses, only one rejected | Only linked rejected item; other hypothesis never labeled rejected. |
| 10 | Rejected advice/action rather than interpretation | No rejected-hypothesis item (explicit boundary may be handled separately). |
| 11 | Partner-causation hypothesis rejected | No blame or “resistance” inferred; preserve exact refusal. |
| 12 | Work-as-solution hypothesis rejected | No automatic work recommendation; preserve exact refusal. |

Also test empty-ledger byte-for-byte request equivalence; four-item selection with older boundaries; `_superseded` and user reopening; /new and cross-user isolation; malformed/mismatched snapshots; short/multisentence/ambiguous rejection false negatives; and evaluator insufficient-context behavior. No new evaluator dimension or live call is required.

## ADR

**Decision.** First implement deterministic, source-linked presentation of already-recognized rejected-assistant-hypothesis events in both recent and older context, while retaining old-only boundary/correction extraction. Make current user words authoritative and test explicit reversal. Do not add a classifier or a broad prompt rewrite.

**Why.** The current recent/old discontinuity is proven by source and offline probe. A small context change can remove that inconsistency while preserving the conservative detector and existing persistence model.

**Alternatives rejected.** Prompt-only cannot recover forgotten evidence; history annotation changes message semantics; response keyword guard is brittle; semantic similarity/extra LLM calls introduce unverified interpretation.

**Risks.** (1) Detector false negatives remain, especially anaphoric refusals; (2) older quoted rejection may lack enough meaning without its assistant text; (3) recent duplicate quote/system placement may overstate authority; (4) later user reopening may not suppress stale memory; (5) four-item competition and read-snapshot mismatch can omit a relevant event. These risks preclude a guarantee against all paraphrased returns.

**Rollback.** Remove the recent-rejection inclusion and its tests; existing older ledger, raw 20-message history, schema, and prompt remain as before.

**First implementation slice.** Conceptually add a narrow selector for existing qualifying rejected-hypothesis events across the current conversation, reuse the bounded labeled runtime-memory renderer, and add offline assembly tests for recent/old parity, empty state, false positives, four-item protection, and explicit user-led reopening. Preserve current event detection patterns. Judge any model compliance or narrow prompt addition separately, using offline qualification before live use.
