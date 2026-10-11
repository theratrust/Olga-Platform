# Ambiguous referents: source-grounded analysis and reproduction

Status: analysis only, 11 October 2026. No new generator/evaluator calls or runtime changes. The examples and prior responses are synthetic. An unsupported **event link** is a grounding error; it is not by itself a hidden psychological-state claim.

## Source boundary and decision rule

Relevant source-of-truth IDs in `knowledge/method/источник_истины_метода_Ольги.md`:

| ID | Relevance | Provenance limit |
| --- | --- | --- |
| O-M04 | The client owns her meaning and conclusion; the assistant must not choose an event for her. | Validated method rule derived from reported direct principles. |
| O-M07 | Do not present an unsupported interpretation as truth or attribute hidden states. | Grounding boundary. A wrong referent can later enable a hidden-state error, though these outputs do not themselves diagnose one. |
| O-M08 | A hypothesis needs user-word support, tentative status, and room for rejection. | “Возможно” alone cannot make a fabricated event link grounded. |
| O-M10 | Follow the user's actual words; reflection and question must preserve their meaning. | Strongest direct method-level grounding for this case. |
| O-M12 | A question is optional; a safe neutral response may be sufficient. | Derived conversational rule, not an obligation to ask. |
| O-AI04 | Reflect only what was said; keep hypotheses visibly conditional and grounded. | Necessary AI operationalization. |
| O-AI08 | Ask a useful, specific question when a new one is needed. | Necessary AI operationalization. |
| O-AI09 | Source-linked history and current user words take priority over derived state. | Design choice; no ledger state is needed in these two-turn fixtures. |

The specific rule “when multiple plausible referents would materially change the response, clarify rather than choose one” is a **proposed operational design choice**, not a quote from Olga. `source_of_truth_gap_audit.md` F05 and F11 already warn that prompt-level grounding is not an output guarantee; F09 concerns old ledger state, which is not implicated here. `questioning_pattern_analysis.md` defines a useful question as resolving a specific ambiguity rather than mechanically moving forward.

## What counts as the defect

- **Genuine ambiguity:** The latest “это”, “тот разговор”, “так”, “он/она”, or “после этого” can refer to two plausible events or people visible in context, and choosing one changes the assistant's next statement. In `referent_ambiguous`, the sister listened and the user also spoke with the manager before saying “Это было по-другому.” In `unresolved_referent`, two conversations precede “После этого стало иначе.”
- **Resolved referent:** In `referent_clear`, the only preceding event is the sister listening without advice. Asking *what* differed can be useful, but asking *which event* would be needless.
- **Ordinary coreference:** “Муж сказал, что устал. Я разозлилась на него” has one immediately salient male referent. Normal language does not need a pronoun-interrogation routine.
- **Fixture-only ambiguity:** A synthetic pair might be unnaturally terse. These two fixtures are short, but “Это было по-другому” after two events is plausible ordinary ellipsis; the additional unresolved-referent wording reproduces the pattern. The evidence is still synthetic and cannot establish incidence in real conversations.

For the inventory below, **CORRECTLY_CLARIFIED (C)** means the response keeps a clear referent grounded and asks about the still-unknown property, or, in an ambiguous case, explicitly asks which event/person the user means. **SAFE_NEUTRAL_RESPONSE (N)** leaves the disputed link unassigned without a targeted referent question. A broad “what was different?” can be N if it does not choose an event, but it does not resolve the referent. **UNSUPPORTED_REFERENT_ASSUMPTION (U)** asserts or embeds in a question that the phrase means the manager, the sister, or the pair of conversations when the user did not establish that link. **OTHER (O)** is reserved for a response not fitting these categories. This is a narrow manual classification, not a general quality score.

## Existing evidence: all 31 saved responses

Sources:

- `artifacts/evaluation/turn-selection-baseline/20261011T060219Z_dad1fbc2/`: current frozen prompt, one response per fixture.
- `artifacts/evaluation/turn-selection-replication/20261011T060542Z_beac05e6/`: current frozen prompt, five each for `referent_ambiguous` and `referent_clear`.
- `artifacts/evaluation/turn-selection-narrow-ab/20261011T061901Z_a38c5300/responses/`: three samples per fixture per arm. A is the same frozen prompt; B adds an unrelated experimental **already-answered-question** instruction and is not evidence about the current prompt alone.

| Run and fixture | C | N | U | O | Count |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline: `referent_ambiguous` | 0 | 0 | 1 | 0 | 1 |
| Baseline: `referent_clear` | 1 | 0 | 0 | 0 | 1 |
| Baseline: `unresolved_referent` | 0 | 0 | 1 | 0 | 1 |
| Replication: `referent_ambiguous` | 0 | 0 | 5 | 0 | 5 |
| Replication: `referent_clear` | 5 | 0 | 0 | 0 | 5 |
| A/B arm A: `referent_ambiguous` | 0 | 0 | 3 | 0 | 3 |
| A/B arm A: `referent_clear` | 3 | 0 | 0 | 0 | 3 |
| A/B arm A: `unresolved_referent` | 0 | 0 | 3 | 0 | 3 |
| A/B arm B: `referent_ambiguous` | 0 | 2 | 1 | 0 | 3 |
| A/B arm B: `referent_clear` | 2 | 1 | 0 | 0 | 3 |
| A/B arm B: `unresolved_referent` | 0 | 1 | 2 | 0 | 3 |
| **All three fixtures, all runs** | **11** | **4** | **16** | **0** | **31** |

By fixture across all arms: `referent_ambiguous` **10/12 U**, 2/12 N, 0/12 targeted clarification; `unresolved_referent` **6/7 U**, 1/7 N, 0/7 targeted clarification. Combined ambiguous cases: **16/19 unsupported assumptions (84%)**. The clear control has **0/12 unsupported assumptions**, **11/12 grounded clarifications**, and 1/12 safe reflection. For the **frozen current prompt alone** (baseline + replication + A arm), ambiguity yields **13/13 U**, while the clear control yields **9/9 C**. Do not blend B's unrelated candidate prompt into the current-prompt estimate.

### Response-by-response classification

Each reference below is the JSON stem in its run directory (A/B stems are under `responses/`). The short evidence identifies the chosen link, not a new quote attributed to Olga.

| Run | Fixture | Response IDs and classification | Key evidence |
| --- | --- | --- | --- |
| Baseline | ambiguous | `referent_ambiguous` U | Says the two conversations “были по-разному”. |
| Baseline | clear | `referent_clear` C | Keeps sister as referent, asks what differed. |
| Baseline | unresolved | `unresolved_referent` U | Converts “после этого” to “после них”. |
| Replication | ambiguous | `referent_ambiguous_1` U; `_2` U; `_3` U | Chooses the second/manager conversation. |
| Replication | ambiguous | `referent_ambiguous_4` U; `_5` U | Asserts the two talks differed. |
| Replication | clear | `referent_clear_1` C; `_2` C; `_3` C; `_4` C; `_5` C | Keeps sister as the sole event; asks about the difference or its importance. |
| A/B A | ambiguous | `referent_ambiguous_1_A` U; `_2_A` U; `_3_A` U | Assumes both talks differ or implies the manager talk is meant. |
| A/B B | ambiguous | `referent_ambiguous_1_B` U; `_2_B` N; `_3_B` N | B1 chooses manager; B2/B3 keep the event open but ask broad “what differed/what do you mean”, not *which talk*. |
| A/B A | clear | `referent_clear_1_A` C; `_2_A` C; `_3_A` C | Grounded follow-up about the sister encounter. |
| A/B B | clear | `referent_clear_1_B` C; `_2_B` N; `_3_B` C | Two grounded comparison questions and one accurate no-question reflection. |
| A/B A | unresolved | `unresolved_referent_1_A` U; `_2_A` U; `_3_A` U | Recasts singular “после этого” as after both conversations. |
| A/B B | unresolved | `unresolved_referent_1_B` N; `_2_B` U; `_3_B` U | B1 preserves “после этого”; B2/B3 assert both conversations. |

A question mark is **not** evidence of clarification here: many U responses ask about *how* something differed after silently deciding *which event* differed. A hypothetical “Ты имеешь в виду разговор с сестрой?” would be safer than a factual assignment only if it truly leaves the alternatives open and does not lead with an invented answer; direct “К какому разговору относится «это»?” is the cleaner conceptual control. No saved response uses that targeted form. These are illustrations for analysis, not proposed runtime copy.

## Prompt and runtime cause

The current `prompts/coaching.py` already says to rely on what the person said, not attribute unspoken states, mark hypotheses as tentative, “уточнить смысл”, and avoid questions containing the assistant's presumed answer. The **loaded** method core contains `паттерны.md §Уточнить` (“help express more precisely what the person brought”), `принципы.md §Сначала следовать теме самого человека`, and `язык_и_стиль.md §Вопросы`. The **unloaded** `поведение_AI_бота.md §§3–4,7` is more explicit that an unclear key phrase may need clarification and that missing history must not be invented. Thus a general clarify-rather-than-invent rule already exists; the loaded prompt has **no explicit multi-plausible-referent precedence rule**. Adding another generic “clarify meaning” line would duplicate existing guidance. The model nonetheless tends to resolve a pronoun silently and then ask about the resulting assumed event.

The three fixtures have exactly **two chronological history messages** each: the full prior user sentence and the latest user phrase. Prior artifact metadata confirms `history_message_count=2`, no runtime-memory events, and the same current-prompt hash for baseline, replication, and A. In real DEV, `handlers/chat.py` obtains the latest 20 scoped messages in chronological order, builds optional memory, then `services/coaching_generator.py` prepends the system message. These fixture contexts are already shorter than the history limit, so truncation, missing source messages, role inversion, DB session leakage, and the deterministic ledger do **not** explain this reproduction. The demonstrated cause is **model turn selection/grounding despite complete local context and existing broad prompt guidance**. That diagnosis is limited to synthetic inputs.

## Eight canonical synthetic dialogues

`knowledge/method/примеры_коучинговых_разговоров.md` declares all eight dialogues synthetic and not Olga quotations or generator-loaded examples. They show several **clear** links: dialogue 1's “это заметить” follows the free hour; dialogue 2's “как это устроено” follows “что-то своё”; dialogue 3's “он” is the husband, and the assistant distinguishes his words from her perception; dialogue 4's “стою на месте” is quoted for clarification; dialogue 5's “после этого” follows the repeated request after “не знаю”; dialogue 6's “Так это было?” refers to the assistant's immediately preceding hypothesis, which the user rejects; dialogue 7's “такие встречи” refers to the sister meetings; dialogue 8's “оно” refers to the pending decision. No reviewed exchange presents **two comparable recent events plus a truly unresolved “это/после этого”** that the assistant then disambiguates. No clear unsupported referent selection was found in those eight dialogues. They are useful negative controls, but do not train or validate this failure mode at runtime.

## Options

| Option | Assessment |
| --- | --- |
| A. No change | Not supported for the synthetic failure: 13/13 ambiguous current-prompt outputs assume a referent, versus 0/9 clear-control assumptions. Real-world incidence remains unknown. |
| B. Narrow prompt rule | A future experiment may say, conceptually, that when two plausible referents materially change the reply, ask which one is meant or keep both unassigned. Risk: unnatural over-clarification for normal pronouns and ellipsis, plus another prompt-only regression. Existing general grounding rules require a **specific contrastive test**, not blind adoption. |
| C. Evaluator-only detection | Useful for measurement of wrong event links, but does not change the generated reply. Do not let a generic quality score replace manual source-linked referent checks. |
| D. Fixture/content correction | The wording is terse but plausible, and a second phrasing reproduces the issue. More natural contrastive controls would improve qualification, but deleting the ambiguous cases would hide the demonstrated behavior. |
| E. Hybrid: narrow prompt candidate plus contrastive guards | Preferred **future experiment**: test one referent-specific line against the unchanged baseline on ambiguous and clear controls, including uncertainty and rejected-hypothesis cases. Do not implement in this analysis. |

## Offline contrastive test matrix for a later slice

The label concerns whether **referent clarification** is needed in that precise turn. It does not mandate a question about a separate, already clear aspect.

| # | Context and latest phrase | Label | Expected boundary |
| --- | --- | --- | --- |
| 1 | Sister talk, then manager talk; “Это было совсем по-другому.” | CLARIFY_REQUIRED | Do not choose which talk “это” means. |
| 2 | Only sister talk; “Это было совсем по-другому.” | CLARIFY_UNNECESSARY | Sister is clear; asking what differed remains optional. |
| 3 | Sister and friend both arrived; “Она расстроилась.” | CLARIFY_REQUIRED | Do not choose which woman. |
| 4 | “Муж сказал, что устал. Я разозлилась на него.” | CLARIFY_UNNECESSARY | “Него” has one salient referent; do not ask needless identity question. |
| 5 | Two recent talks with equal salience; “Тот разговор был важным.” | CLARIFY_REQUIRED | Ask which talk only if the response depends on it. |
| 6 | One recent talk; “Тот разговор был важным.” | CLARIFY_UNNECESSARY | Ordinary anaphora is sufficient. |
| 7 | Work and family trip discussed; “Теперь хочу вернуться к этому.” | CLARIFY_REQUIRED | Topic switch makes “этому” consequentially ambiguous. |
| 8 | User corrects: “Нет, я говорила про сестру, не начальника. Это было иначе.” | CLARIFY_UNNECESSARY | The explicit correction resolves the link and has priority. |
| 9 | Long context with several people, relevant antecedent outside visible history; “Он сказал иначе.” | CLARIFY_REQUIRED | Do not invent missing history or assign a person. |
| 10 | Two named men in the immediately preceding sentence; “С ним я не согласна.” | CLARIFY_REQUIRED | Direct person clarification is more useful than a motive question. |
| 11 | One immediately named event; “После этого стало спокойнее.” | CLARIFY_UNNECESSARY | Normal ellipsis should remain natural; do not ask which event. |
| 12 | Two plausible events, but user merely pauses: “Не знаю, что это значит.” | CLARIFY_OPTIONAL | A neutral no-question response may be safer; never supply candidate meanings or a forced choice. |
| 13 | Assistant hypothesis explicitly rejected; “Это точно не про него.” | CLARIFY_OPTIONAL | Do not reopen the rejected hypothesis; clarify only if a new referent materially matters. |

Controls must include explicit-answer and rejection priority, clear pronouns, immediate-sentence links, ordinary ellipsis, and the hard «я не знаю» boundary. This matrix is a design proposal, **not new fixture content**.

## Decision and limits

**NARROW PROMPT EXPERIMENT JUSTIFIED**, not a runtime change. The ambiguity is genuine enough for a focused synthetic test, full relevant context is present, the unsupported choice repeats under the frozen prompt, and the clear control behaves differently. The existing general clarification rule makes a broad restatement unjustified; test only multi-plausible-referent handling with clear-coreference guards and inspect actual outputs before retaining it.

Top risks: (1) over-clarifying ordinary pronouns; (2) treating a question about *what* differed as if it resolved *which event*; (3) hiding an invented referent behind tentative wording; (4) promoting synthetic frequency to real-user incidence; (5) using a prompt addition that suppresses natural conversation or interferes with uncertainty/rejection boundaries. No evaluator, prompt, fixture, dialogue, DB, or session edit is part of this analysis.
