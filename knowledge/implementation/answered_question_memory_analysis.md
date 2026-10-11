# Already-answered questions and the 20-message boundary

Status: static method/runtime analysis plus review of saved generator artifacts, 11 October 2026. No runtime, prompt, evaluator, fixture, or database change is proposed as an established Olga technique.

## Source and authority

The repository has no independently verifiable Olga interview or real Olga conversation (источник_истины_метода_Ольги.md, layer A). The following are validated or derived project rules, **not** direct quotations from Olga:

| IDs | Product basis | Status for this analysis |
| --- | --- | --- |
| O-M04, O-M10 | Follow the client's words and preserve her authorship; questions must not impose an already displaced frame. | Validated method rules in the project. |
| O-M05–06 | Do not force an answer or fill «я не знаю» with candidate content. | Validated/product hard boundary; uncertainty is not an answer. |
| O-M12 | A question is not required on each turn. | Derived method rule. |
| O-AI08 | Take account of what was already answered; do not ask for form's sake. | Necessary operationalization, not a specification of long-term memory. |
| O-AI09–10 | Use verifiable conversation evidence and current-message priority; avoid questionnaire-like repetition. | Reversible product design choices. |
| O-U07–08 | Synthetic dialogue turns, the 20-message window, and ledger design are not Olga-authored method facts. | Provenance limit. |

The behavior document (§§7–10,18), questioning_pattern_analysis.md, and turn_selection_fixtures.md support distinguishing a useful new clarification from an already-answered question. They do not prescribe persistent answered-question records. A durable, capped record would be an engineering choice under O-AI09, not a direct or validated Olga rule.

## What is actually “answered”?

Use three distinct claims. (1) The user **responded after** a question: observable adjacency only. (2) The response **explicitly supplies the requested information**: sometimes recognizable from the words, but not generally decidable without interpreting meaning. (3) The topic is **closed forever**: never justified by a past answer. A conservative deterministic system should not promote claim 1 to claim 2 or 3.

| Shape | Safe inference | Unsafe inference |
| --- | --- | --- |
| Single explicit assistant question followed immediately by substantive, on-topic user wording, e.g. «Что для тебя сейчас самое тяжёлое?» → «Полная зависимость от мужа.» | Preserve the exact source-linked Q→response pair as evidence; for a closely matching literal re-ask, this can show that the same question previously received this answer. | Declare all semantically similar questions answered, infer a hidden cause, or treat the answer as permanent. |
| Multi-part question, one dimension answered | At most remember the literal response and which part it explicitly names, if unambiguous. | Mark the compound question fully answered. |
| Open prompt «Расскажи подробнее» → user response | The user contributed content. | Create a closed, answerable question slot. |
| Rhetorical/reflective question, assistant statement containing “?”, or candidate-answer question | Preserve raw history as usual. | Assume the user's next turn answers a stable factual question. |
| Explicit «Я уже отвечала на это» | User has corrected the assistant's repetition; if the immediately preceding assistant question is identifiable, link the correction to that exact question. | Invent the missing earlier answer or suppress all future inquiry on the topic. |
| Later «Теперь я думаю, что всё-таки хочу» after «Я не хочу работать» | Current explicit statement wins. | Keep the old statement as current truth or infer a causal change story. |

A bare «да»/«нет» may answer a clear binary question locally, but has poor portability once source context is gone; it is not a safe general carry-forward item. «Не знаю», a refusal, a topic shift, and silence are **not** substantive answers. False negatives are preferable to telling the model that the user answered something she did not.

## Current runtime trace

- Private text and original-marker voice transcription converge on the coaching path. The admitted user turn is stored before generation. handlers/chat.py loads get_recent_history(user_id, conversation_id, limit=20), then get_conversation_history_with_ids(user_id, conversation_id), calls build_carry_forward(source_rows, history), renders its optional block, and passes raw history plus block to build_messages. Moderated drafts use the same candidate-generation path. The fixed acknowledgement and observers do not select the next question.
- database.py selects the latest 20 rows by descending id, reverses them into chronological role/content history, and scopes both this read and the all-rows ledger read by **user_id + conversation_id**. The latter has no row limit within the current conversation. A new /new conversation cannot recover deleted earlier rows.
- services/coaching_generator.py adds runtime memory to the system instruction only when nonempty; otherwise the system message and history are unchanged. The generator has max_tokens=350. No runtime question selector, answer index, or output de-duplication exists.
- services/conversation_state.py validates ascending source ids and an exact match between the all-rows tail and the raw history. On mismatch it emits no memory. Its maximum is four deduplicated events. It recognizes a linked explicit rejection of a tentative assistant hypothesis in recent **or** old history. It recognizes certain explicit user boundary/correction wording **only when older than the raw window**. It does not create answered Q/A events.
- The boundary pattern includes «я уже говорила/говорил/сказала/сказал» when a short, self-contained quote has content tokens and passes uncertainty checks. It does **not** explicitly recognize «я уже отвечала/отвечал». When an old «я уже говорила: …» survives, it is a generic user_boundary_or_correction with a user quote, not a link to a question or an “answered” flag. A recent one is raw history only. The rejection machinery links an assistant hypothesis to a user rejection and has narrow lexical supersession; reusing it as answered-question detection would confuse two different assertions.
- The all-rows query means a deterministic extension **could** see older in-session pairs without a DB schema change. No separate ledger is persisted. Its current empty-state behavior leaves generator inputs unchanged. These properties should remain invariants of any experiment.

The source_of_truth_gap_audit.md F13 already names the deliberately omitted answered-item ledger. F12 and questioning_pattern_analysis.md separately name question-selection pressure. Neither proves an observed old-window repeated-question incident.

## Saved failure evidence: a visible pair, not memory loss

The repeated_answer fixture provides, in order: assistant «Что для тебя значит „своё“?», user «Самой выбирать, как устроен день.», assistant re-ask «А что для тебя значит „своё“?», then current user «Я уже говорила: самой выбирать, как устроен день.» All four turns fit within the latest 20; the source pair is present in the fixture input.

| Saved run | Current-prompt observations | Interpretation |
| --- | --- | --- |
| turn-selection-baseline/20261011T060219Z_dad1fbc2 | 1/1 acknowledged the correction and asked «Что сейчас мешает тебе это делать?» | New barrier question, not a literal repeat; this turn was labelled QUESTION_AVOID. |
| turn-selection-replication/20261011T060542Z_beac05e6 | 5/5 acknowledged; 5/5 asked another low-value question; 0/5 useful new question; 0/5 no-question response. | Recurrent automatic continuation **despite** visible answer/correction; none was a verbatim re-ask. One sample assumed an unstated obstacle. |
| turn-selection-narrow-ab/20261011T061901Z_a38c5300 | Frozen arm A: 3/3 low-value new questions, including one syntactic question missing “?”. Experimental arm B: 1/3 low-value question and 2/3 grounded no-question responses. | Narrow prompt instruction improved this fixture in a small experiment but did not eliminate the behavior. Arm B is **not** the runtime prompt; this analysis makes no prompt recommendation from question-mark counts alone. |

These artifacts establish a visible-context **turn-selection** weakness, not a case where the answer fell outside the raw window. They do not establish a rate of literal repeats or near-equivalent re-asks in long sessions. “Already answered” must not mean “never ask another question”; a genuinely new, grounded clarification remains allowed.

## Window scenarios

1. **Pair inside latest 20.** The generator receives exact Q and A in chronological raw history. If the current user says «Я уже говорила: …», those words are visible too. There is currently no explicit answered-question metadata. The observed failure occurred here. A new source-linked event could make evidence salient, but it would duplicate some raw content and cannot force the model to choose a good next move.
2. **Same pair outside latest 20.** The raw Q and A disappear. The all-rows ledger read still sees them within the active conversation, but today's detector does not emit an answered item. Unless a separate qualifying old boundary/correction survives, the model has no Q/A evidence. An exact short Q+response event could span this boundary; broad semantic equivalence still would not follow.
3. **Old pair, correction in latest 20.** «Я уже отвечала на это» appears as current raw user text, but the current ledger does not recognize that phrase or retrieve the answer for it. «Я уже говорила: [content]» may later become an old generic boundary item if it passes lexical safeguards. A portable correction event should link to the **immediately preceding re-ask**, when available, and quote only the correction; without the old answer it must say “user flagged this question as previously answered,” not “answer was X.”

Across the 20-row edge, identical source evidence should yield the same narrow *meaning* if an event is introduced, while recent raw messages remain unchanged. The newest explicit user statement, including an update to an earlier answer, always outranks an old Q/A pair. A conservative system cannot safely invalidate every superseded answer by semantic matching. It can avoid presenting any Q/A as permanent and can suppress an older event when an explicit later correction repeats distinctive source terms; otherwise the present user turn wins in the model-facing wording, with stale-memory risk documented.

## Feasible representations and limits

No DB schema or new model call is required to experiment: the full scoped source rows and ids already exist. The question is whether a candidate event can be **trusted** enough to show the generator.

| Representation | Utility across window | Cost and failure mode |
| --- | --- | --- |
| A. Full short question + verbatim response + source ids | Best support for exact-repeat avoidance and user authorship; recent/old wording can match. | Two quoted spans consume tokens; adjacency alone does not prove completeness; old answer can go stale. Apply short length bounds and small cap. |
| B. Extractive fragments from each | Lower token cost. | Selecting fragments silently changes meaning and needs semantic judgement; unsafe as the first slice. |
| C. Question text + “answered” | Low tokens; supports literal-repeat warning. | “Answered” overclaims from mere adjacency; no evidence of what the user said. Use only if correction explicitly says answered. |
| D. User response only | Preserves user wording at low cost. | Cannot tell which inquiry it responded to; may look like a present belief. Existing generic correction ledger partly does this. |
| E. No new event | Zero context cost, empty-state invariant. | Old Q/A pair is lost; visible-context failure persists too. |

A strict adjacent-Q→A extractor could emit a **question-and-response record**, not a “fully answered fact”: exactly one short, interrogative assistant turn; next row is a substantive self-contained user response; reject multi-part questions, candidate-answer prompts, «не знаю», bare assent/refusal, topic changes, and malformed content. Even this cannot reliably establish topical relevance or completeness without semantic inference. It can help literal repeats and perhaps very close lexical repeats; it cannot promise detection of paraphrases or of information supplied in a non-adjacent user turn. Pure string normalization (spacing/case/punctuation) is safe; lexical overlap is evidence, not proof of equivalence. Do not hard-block generated questions with keyword matching.

A 3–4 item shared cap, bounded verbatim spans, ids of both source rows where present, deduplication, and data-not-instructions marking would fit the current ledger style. There is no justified token number yet; measure with representative Russian pairs before implementation. Four full 180-character Q/A pairs could be materially larger than today's user-only events. Do not log raw Q, A, user id, or conversation id.

## Options and recommendation

| Option | Benefit | Main limit | Verdict |
| --- | --- | --- | --- |
| A. Raw 20 only | No false ledger facts or token growth. | Cannot recover old Q/A; did not prevent observed visible-context continuation. | Insufficient for long-window risk. |
| B. Explicit user correction event only | Strong user-authored evidence; links a re-ask to «я уже отвечала/говорила» without claiming to infer answer semantics; can be surfaced recent and old. | Does not prevent old literal repeats before the user complains; standalone correction may lack the original answer. | **Recommend as first, smallest deterministic slice.** |
| C. Conservative adjacent Q→A memory | Could prevent exact re-asking before complaint, across the window. | Adjacency is not proof of a full answer; stale/multipart/short replies create false positives. No observed old-window repeated-question failure yet. | Qualify separately before adding. |
| D. B plus C | Strongest potential coverage. | Adds two detector types and a shared cap before the weaker C rule is qualified. | Premature for first slice. |
| E. Narrow prompt rule only | The saved A/B arm suggests some help for visible correction. | Cannot reconstruct vanished Q/A evidence and B still failed 1/3; prompts are not deterministic memory. | Not needed for the proposed first slice. |

**Decision: B — explicit-correction memory only**, as a source-linked, conservative product-quality experiment. It directly targets the observed correction case and can survive the 20-message edge without pretending to know an old answer. Do not call it a complete solution to old-window re-asking. The next gate for C is deterministic fixtures proving precision on direct, partial, refusal, uncertainty, topic-shift, and update cases, plus actual long-window repeated-question evidence. A prompt change is **not necessary** to implement or test B; the saved prompt experiment is separate evidence about response selection, not proof that memory alone will fix it.

**First implementation slice, conceptual only:** one narrowly named correction event in conversation_state.py for explicit «я уже отвечала/отвечал» and existing self-contained «я уже говорила/говорил …» forms, only when a particular immediately preceding assistant re-ask is identifiable and the correction is unambiguous. Carry the assistant source id/question quote plus the user's source id/exact correction, no invented prior answer. Surface it consistently recent and old; retain the existing four-item cap and recent-history source check. Preserve unchanged inputs when no qualifying correction exists. Make its wording a warning against simply re-asking that source question, never a ban on all new questions. Add offline detector/window, false-positive, current-message-priority, and context-size tests before any model measurement. No changes are made in this task.

## User updates and false-positive safeguards

- The correction event reports **what the user said and which assistant re-ask triggered it**. It never states an inferred “real answer.” A later user-authored update has priority even if it conflicts with an older answer.
- A repeated exact question can be compared against quoted source text. Near-identical wording may be highlighted only when a conservative surface match is evident; semantic paraphrase and supplied-information detection remain model judgement, not deterministic guarantees.
- Require one identifiable assistant question; reject mixed statements, rhetorical questions, several questions, open prompts, and opaque/overlong quotes. An explicit correction with no identifiable target can stay in raw history, but must not be turned into a portable answered-question prohibition.
- Do not equate rejection of a hypothesis, refusal to answer, «не знаю», a generic «нет», or a topic shift with “already answered.” Preserve the rejection detector's separate semantics and false-positive policy.
- Do not record an old answer as timeless fact. If a later user statement explicitly revises it, foreground that later statement; if lexical linkage is unsafe, omit/suppress the old event rather than guessing. If an update's relation is only semantic, record the limitation.
- Cross-/new data stays excluded by the existing user_id + conversation_id reads; no separate persistence table is proposed.

## Offline test matrix for a later slice

Outcomes refer to a *portable answered/correction event*, not whether the raw user text remains in history. “UNRESOLVED” means the system should avoid claiming completeness.

| # | Fixture shape | Expected outcome | Why |
| --- | --- | --- | --- |
| 1 | Single question → explicit substantive answer, adjacent | UNRESOLVED under B; candidate Q/response evidence under C | Response is visible, but completeness needs qualification. |
| 2 | Same pair inside latest 20 | UNRESOLVED under B absent correction | Raw pair is present; do not invent metadata. |
| 3 | Same pair beyond latest 20, no correction | UNRESOLVED under B | B cannot reconstruct it; C could only after separate gate. |
| 4 | Re-ask → «Я уже отвечала на это» | USER_CORRECTION_ONLY | Source-link the immediately preceding re-ask; do not infer old answer. |
| 5 | Literal repeated assistant question, then explicit correction | USER_CORRECTION_ONLY | Exact source text may be carried as repeat evidence. |
| 6 | Paraphrased but semantically similar re-ask | UNRESOLVED unless user explicitly flags it | No semantic-equivalence claim. |
| 7 | User supplies new detail; assistant asks genuinely new grounded follow-up | DO_NOT_REMEMBER as a closed slot | A prior answer does not prohibit further inquiry. |
| 8 | Multi-part question; user answers one part | UNRESOLVED | Never mark whole question fully answered. |
| 9 | Question → «Не знаю» | DO_NOT_REMEMBER | Hard uncertainty rule; no candidate answer. |
| 10 | Question → «Не хочу отвечать» | DO_NOT_REMEMBER as answered | Refusal is its own boundary, not answer content. |
| 11 | Question → bare «да» or «нет» | UNRESOLVED for portable memory | Context may be lost. |
| 12 | Question → unrelated topic switch | DO_NOT_REMEMBER | Adjacency is misleading. |
| 13 | Old answer → later explicit changed answer | UNRESOLVED or suppress old event | Newest user statement wins; no permanent truth. |
| 14 | Two prior Q/A pairs, user flags only one re-ask | USER_CORRECTION_ONLY for that one | Do not close the other. |
| 15 | More than four eligible explicit corrections | USER_CORRECTION_ONLY, capped at four | Keep recent source-linked evidence. |
| 16 | No qualifying correction | DO_NOT_REMEMBER | Byte-equivalent empty-state generator inputs. |
| 17 | Old original question/answer, recent «Я уже отвечала» after a re-ask | USER_CORRECTION_ONLY | Surface correction without inventing inaccessible answer. |
| 18 | Recent correction moves beyond raw 20 | USER_CORRECTION_ONLY | Same event meaning and source ids across cutoff. |
| 19 | Statement with a quoted “?” rather than one genuine assistant question | DO_NOT_REMEMBER | Avoid false assistant-question slots. |
| 20 | Current user explicitly revises an old answer | UNRESOLVED old event; current user wins | No lexical rule may override new explicit wording. |

For a future C study, label the strongest direct Q→A example REMEMBER_ANSWERED only after a separately reviewed definition of “explicitly supplies requested information” passes these negative controls. This matrix deliberately does not assume that adjacency alone meets that standard.

## Canonical and evaluator implications

The eight “canonical” conversations are synthetic, not real Olga speech. Their closing notes say history should change the next turn, a question is not mandatory, and an already answered question should not be disguised by new wording (примеры_коучинговых_разговоров.md §Что эти примеры показывают для AI-бота). Dialogue 2 repeatedly uses “what does X mean?” and could model a mechanical cadence; dialogue 5 explicitly models not repeating a question after uncertainty. This is mixed illustrative content, not proof that the runtime re-asks old answers; the dialogues are not loaded into the generator.

The method evaluator does not demand a question or fixed progression and can penalize loss of client authorship, but has no dedicated source-linked “already answered” hard fail. The quality rubric's non_repetition, contextual_specificity, question_quality, and Q03/Q05 can disfavor repetition; it explicitly allows a useful no-question turn. Its progression dimension could still reward an unnecessary next question in borderline scoring, a **measurement risk**, not a proven runtime incentive: observers run after candidate creation and do not alter the reply. turn_selection_fixtures.md labels repeated_answer QUESTION_AVOID and notes that current scalar evaluator dimensions cannot encode USEFUL/OPTIONAL/AVOID as a direct turn-selection distinction. No evaluator changes are recommended here.

## Top five risks

1. False “answered” claims from adjacent but partial, irrelevant, or uncertain replies.
2. Stale old Q/A text overriding a later user-authored update.
3. Treating a correction against one repeated question as a global ban on useful follow-ups.
4. Extra token load and crowding from verbatim Q/A pairs or duplicate recent history.
5. Confusing the measured visible-context continuation failure with an unmeasured old-window literal-repeat failure, then changing the wrong mechanism.

