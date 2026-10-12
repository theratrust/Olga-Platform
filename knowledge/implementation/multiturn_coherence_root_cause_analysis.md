# Multi-turn coherence: offline root-cause analysis

Scope: branch feature/method-core; frozen run 20261011T_multiturn_frozen_01; six synthetic trajectories, 66 accepted assistant turns. This is analysis of saved text and repository assembly, with zero new model or evaluator calls. Three incomplete replies are coded OTHER and excluded from semantic-question counts; their reliability cause is outside scope. Scripted later user turns need not answer the generated question, so later user insight is not automatically credited to the bot. The aim is to choose the action fitting the current turn and trajectory, not to reduce question marks.

## 1. Trajectory reconstruction

Tn means the assistant response to scripted user turn n. A first LOCAL_QUALITY_GOOD_BUT_TRAJECTORY_STALLS label marks the earliest locally plausible response whose function is redundant or fails to hold a useful distinction; it is an independent trajectory judgement, not a fixture tag.

| Scenario | Good start and first stall | Later trajectory |
| --- | --- | --- |
| identity_after_relocation | T2–T4 follow her correction from husband and friends to her own place. **T7** first stalls: after she distinguishes chosen time from busyness, the grounded reflection is followed by broad “Что ты сейчас замечаешь в этом выборе”. | Questions dominate T1–T10. T9 adds a genuinely new inquiry into the solo walk; T10 asks for more noticing after a provisional insight. She authors “choose part of the week” and later “the city can be mine”; the bot preserves both but contributes little after the distinction. Repetition clusters T7–T10 rather than rising monotonically. T11 accepts closure. |
| uncertainty_unknown | T1–T4 safely allow uncertainty without a question. **T5** first stalls in a different way: it paraphrases “чужая фраза” without increasing precision; T6 does the same with the cafe. | No questions anywhere. T8–T9 closely mirror new wording. The user herself introduces “тесно” and distinguishes lack of her own time from number of tasks. The bot holds it and stops at T11. This is reflection-only monotony, not a reflect→question loop. |
| rejected_hypothesis_reopening | T2 respects rejection of fear; T3–T4 explore schedule and contrasting invitations. **T5** first stalls by asking what mattered about Lena compared with declined invitations just after T4 asked what differs between liked and declined meetings. | T6 revisits the same comparison, T7 asks for a choice aid although “with whom and why” is named. T8 legitimately follows the user's bounded reopening; T9 again asks what she noticed about unfamiliar people after she has supplied the unusual fact. T10 offers an optional continuation after she formulates two cases. Questions continue T1–T10. The user authors the two-case distinction; T11 stops. |
| rich_reflection_question_discipline | T2 appropriately ends after reflecting a self-chosen morning. **T3** first stalls: after she names an unscheduled part of the day, “Что ещё ты замечаешь” seeks more material without an open referent. | T4 usefully shifts to quick agreement; T5 correctly clarifies sister versus colleague. T6–T9 hold and assemble the user's insight without questions. Her T8–T9 distinction is clear: hear herself before replying, not always refuse. T10 contains a new uncertainty but the saved response is incomplete, so its question utility is not judged. No increasing question loop here; T11 respects pause. |
| answered_question_continuity | T1–T2 establish what “own time” means. **T3** is the first mild stall: it revisits what happens to choice despite her concrete chosen-evening example and prior definition. T4 is a stronger, separate error: “what the imagined justification protects” inserts an unsupported protective motive. | T5 recasts her correction as another noticing question; T6 acknowledges “already answered” but asks what to *do* with the habit. T7–T9 follow new material better. At T10 she authors the clearer distinction: choose how much to explain and to whom. The bot asks to relate it back to the opening, circling that achievement. T11 honors stop. Repetition is episodic. |
| partner_work_autonomy | T1 keeps the decision hers. **T2** first stalls: after she says lack of pressure does not create clarity, “what do you already see” has no precise target. | T3 can usefully ask about career, but T4 re-asks that dimension after she rejects busyness as self-worth. T5 opens personally owned time; T6 asks for another abstraction immediately after her correction to choosing attention. T7 separates move and own-time decisions; T8 usefully asks what her priority means. T9–T10 keep asking around two named priorities and then a clear contract-versus-work distinction. User answers materially change topic and constraints, while response mode remains reflection→question T1–T10. T11 accepts “enough today.” Repetition recurs, not monotonically. |

Useful questions remain real: identity T9, rich-reflection T5, and partner T8 resolve open material. The failure is mode selection after a sufficient user-authored distinction.

## 2. Response-shape sequencing

Coding: one dominant shape per turn. REFLECTION_QUESTION is a grounding restatement plus inquiry; CLARIFICATION is a narrow factual/referent check; INTERPRETATION_QUESTION introduces a model hypothesis; OTHER covers bare acknowledgements/closures and three incomplete outputs. The first answered-question reply has two surface questions but one dominant shape and one main function. This is analysis-only coding, separate from fixtures.

| Shape | Count |
| --- | ---: |
| REFLECTION_ONLY | 16 |
| REFLECTION_QUESTION | 39 |
| ACKNOWLEDGEMENT_QUESTION | 1 |
| INTERPRETATION_QUESTION | 1 |
| QUESTION_ONLY | 0 |
| CLARIFICATION | 1 |
| DIRECT_ANSWER | 0 |
| OTHER | 8 |
| **Total** | **66** |

Dominant per scenario: identity 8/11 REFLECTION_QUESTION; uncertainty 9/11 REFLECTION_ONLY; rejected hypothesis 9/11 REFLECTION_QUESTION; rich reflection 6/11 REFLECTION_ONLY; answered question 9/11 REFLECTION_QUESTION; partner/work 10/11 REFLECTION_QUESTION. The longest exact REFLECTION_QUESTION run is **partner T1–T10, 10 turns**. Grouping acknowledgement/question and interpretation/question as “setup plus question,” rejected-hypothesis and answered-question also run T1–T10. The shared action cadence matters beyond sentence style.

Descriptive “rich user-authored” subset: identity T2,4,7,8,10; uncertainty T7–T10; rejected T4,6–10; rich-reflection T2–T4,6–T10; answered T2,3,5,6,8–10; partner T4–T7,9,10. These turns explicitly distinguish, correct, or substantially self-observe. REFLECTION_QUESTION follows **25/36** versus **14/30** other turns. It is not uniform: uncertainty 0/4 and rich-reflection 2/8 versus answered 7/7 and partner 6/6. This hand-coded subset is descriptive, not a population estimate.

**One strict meaningful question loop of at least three assistant turns:** rejected-hypothesis T4–T6. T4 asks what differs between liked and declined meetings; T5 asks what mattered in Lena's meeting compared with declined invitations; T6 asks how the same difference changes her view. The user's example and “with whom and why” change the wording, not the conversational function. Long same-shape runs elsewhere include real new dimensions and are not counted wholesale. Near loops of only two complete questions occur at partner T3–T4/T9–T10, answered T2–T3/T5–T6, and identity T7–T8 (the latter includes an incomplete output).

## 3. Semantic progression of questions

One main function for each of 42 complete substantive question turns (19 useful + 8 optional + 15 low-value in frozen manual review). Incomplete fragments at identity T6/T8 and rich-reflection T10 are excluded. Key: CR=CLARIFY_REFERENT, CF=CLARIFY_FACT, D=DEEPEN_USER_AUTHORED_IDEA, N=OPEN_NEW_DIMENSION, F=ASK_FOR_FEELING, M=ASK_FOR_MEANING, A=ASK_FOR_ACTION, P=ASK_FOR_PRIORITY, R=REASK_ESTABLISHED_AREA, G=GENERIC_CONTINUATION, O=OTHER. An asterisk indicates frozen LOW_VALUE_QUESTION.

| Scenario | Turn → function |
| --- | --- |
| identity | T1 D; T2 CR; T3 D; T4 CR; T5 M; T7 G*; T9 CF; T10 G |
| uncertainty | no questions |
| rejected hypothesis | T1 N; T2 G; T3 CF; T4 D; T5 R*; T6 R*; T7 A*; T8 D; T9 R*; T10 G |
| rich reflection | T1 M; T3 G*; T4 D; T5 CR |
| answered question | T1 CR; T2 D; T3 R; T4 M*; T5 G*; T6 A*; T7 D; T8 G; T9 D; T10 R* |
| partner/work | T1 P; T2 G*; T3 M; T4 R*; T5 N; T6 G*; T7 P; T8 M; T9 G*; T10 R* |

| Function | Count | Low-value |
| --- | ---: | ---: |
| CLARIFY_REFERENT | 4 | 0 |
| CLARIFY_FACT | 2 | 0 |
| DEEPEN_USER_AUTHORED_IDEA | 8 | 0 |
| OPEN_NEW_DIMENSION | 2 | 0 |
| ASK_FOR_FEELING | 0 | 0 |
| ASK_FOR_MEANING | 5 | 1 |
| ASK_FOR_ACTION | 2 | 2 |
| ASK_FOR_PRIORITY | 2 | 0 |
| REASK_ESTABLISHED_AREA | 7 | 6 |
| GENERIC_CONTINUATION | 10 | 6 |
| OTHER | 0 | 0 |
| **Total** | **42** | **15** |

Low-value clusters in REASK_ESTABLISHED_AREA (6/7), GENERIC_CONTINUATION (6/10), and premature ASK_FOR_ACTION (2/2). Semantic repeats can change grammar: rejected T4 “what differs?” → T5 “what mattered compared with declines?” → T6 “how does the difference help?”; partner T3 “what matters in career?” → T4 “what matters beyond busyness?”; answered T5 “what do you notice about the habit?” → T6 “how do you want to deal with it?” after she flags the earlier answer. The last pair shifts from noticing to action, so it is a near loop rather than a literal re-ask.

## 4. Exact loaded prompt and provenance

The system-message path is handlers/chat.py → services/coaching_generator.build_system_instruction → prompts/coaching.py:build_coaching_prompt → services/methods/loader.py:load_method_core. It contains DEFAULT_SYSTEM_PROMPT, sanitized first-name/optional archetype data, and exactly five files: метод_Ольги.md, принципы.md, границы.md, паттерны.md, язык_и_стиль.md. build_messages can append rendered ledger data, then recent role/content history. The behavior document, map, and examples are **not loaded**. “Direct Olga” below means *reported as confirmed* in secondary method files; источник_истины_метода_Ольги.md finds no independently available primary transcript.

| Loaded wording / source | Incentive | Provenance |
| --- | --- | --- |
| Base: “не решить проблему … помочь … услышать себя и прийти к собственному ответу”; “Не решай … не говори … что нужно делать”; no automatic variants even on direct advice request. Loaded method/principles repeat it. | Avoid advice; preserve authorship. | DIRECT_OLGA_RULE as secondary files report it; not independently verified. |
| Base: “Опирайся … на то, что человек действительно сказал”; do not attribute motives/emotions; “Интерпретация не является фактом”; hypothesis must be grounded, tentative, rejectable. Loaded boundaries/style reinforce it. | Grounded reflection is safe; strong interpretation is constrained. | VALIDATED_METHOD_RULE / documented working interpretation. |
| Base: “Не заполняй отсутствие ответа”; after “я не знаю” no candidate states even as questions; leave space. Loaded principles/patterns include staying with uncertainty. | Explicit no-question holding in uncertainty. | VALIDATED_METHOD_RULE, with DERIVED_OPERATIONAL_RULE for exact hard wording. |
| Base menu: “отразить”, “уточнить смысл”, “углубить тему”, check contradiction/hypothesis, help formulate; “возможные … не обязательная последовательность”. Loaded method working process/patterns mirror it; patterns explicitly deepen via a question. | Reflection, clarification, deepening, progression toward articulation, without a turn-level choice rule. | DERIVED_OPERATIONAL_RULE. |
| Base: “Помогай ему исследовать то, что он сам приносит”; “Вопрос должен помогать … исследовать”; “Не превращай разговор в анкету или серию вопросов подряд”. Loaded style repeats grounded question quality. | Inquiry is available while mechanical series is forbidden. | DERIVED_OPERATIONAL_RULE; anti-survey cadence is PRODUCT_DESIGN_RULE. |
| Base: “Говори спокойно, естественно”; loaded style favors grounded reflection. | Tone, not mode selection. | PRODUCT_DESIGN_RULE supported by method style. |
| One question at a time; acknowledgement/closure as peer modes. | **No affirmative one-question-per-turn or peer-mode rule is in the loaded prompt.** Unloaded map/behavior document says question optional, usually at most one focused question. | DERIVED_OPERATIONAL_RULE, unloaded. |

The suggested combination “do not advise + do not interpret strongly + continue exploring + ask one question” exists only **partly**. The first two are explicit; exploration is explicit as goal/menu; *ask one question* is not an affirmative loaded rule. Still, a grounded reflection plus inquiry is a low-risk way to appear helpful under the constraints. That is an inference from wording and output, not proof of an intended mandate. Counter-incentives are real: no survey, no mandatory sequence, space after “я не знаю.” Uncertainty and rich-reflection demonstrate that the model can obey those. The gap is mode calibration in ordinary already-clear turns.

## 5. Conversation-map audit

карта_коучингового_разговора.md labels its nine stages, transition signs, examples, history rules, and optionality as *derived product implementation*, not recorded Olga sequence. Stage headings and “how to know one may move on” can visually suggest advancement; stages 3 and 6 show meaning/deepening questions. Its prose explicitly rejects a rigid funnel, permits returning, staying, skipping stages, and finishing without action. Stage 4 permits a pause without question; stage 5 names the danger of paraphrase plus repeated question; stage 7 permits acknowledgement of user clarity without another question; stage 9 supports closure. Staying with a clear distinction and chosen pause are represented. Literal system silence is not an implemented state, but conversational pause and closure are represented. The map does **not** require every turn to move or ask. It can indirectly shape design expectations, but is not a direct runtime cause because it is unloaded. The loaded operational menu shares its exploratory vocabulary but gives less explicit guidance for choosing no-question mode.

## 6. Synthetic-example audit

All eight dialogues in примеры_коучинговых_разговоров.md are invented implementation examples, six assistant turns each: **48 turns; 18 question-ending, 30 no-question**. Structural coding: 15 QUESTION_ONLY; 2 REFLECTION_QUESTION; 1 INTERPRETATION_QUESTION (tentative hypothesis check); 7 REFLECTION_ONLY; 23 other no-question acknowledgements, boundaries, permissions, or closures. The reflection→question turns are dialogue 3 exchange 4 and dialogue 4 exchange 4; dialogue 6 exchange 3 is the separate interpretation→question; no three-turn consecutive reflection→question run. Consecutive *question-only* runs do occur: dialogue 1 exchanges 1–2 and 4–5; dialogue 6 exchanges 1–3. Dialogue 2 asks tidy meaning questions at exchanges 1,3,5. These can suggest a clarify/deepen cadence if treated as scripts, but the distribution is more varied and more no-question oriented than runtime's 42/66 question endings.

Examples show stopping after reflection (dialogue 1 exchanges 3/6), acknowledging without moving (dialogues 4/5), clarification (1/3/8), deeper exploration (2/6/7), direct bounded response rather than advice (3 exchanges 3/6), and natural closure (4/8 exchange 6). They are not Olga transcripts. load_method_core omits this file; **they cannot directly cause runtime generation**. They can influence future design/optimization if humans use them.

## 7. Evaluator incentive audit

качество_ответов_оценка.md scores contextual_specificity, progression, naturalness, and question_quality. “Progression” could be mistaken for another investigative question, while “question quality” makes asking salient. The same rubric grants a useful no-question response full question-quality credit, says no new question/topic is required, and flags repetitive structure and generic questions. метод_Ольги_оценка.md places method boundaries and authorship before style and says no hypothesis, question, or fixed sequence is required. Local scalar assessment may miss long semantic loops: an **optimization/measurement** risk.

handlers/chat.py invokes shadow observers only after candidate generation and delivery/draft creation; the frozen manifest records zero evaluator calls. The quality specification itself says offline. **CAUSE_OF_GENERATION: none demonstrated; evaluator output cannot affect this candidate. CAUSE_OF_WHAT_WE_OPTIMIZE_FOR: plausible** if future changes are selected by local progression/question scores without trajectory review. No evidence shows evaluator scores created the frozen pattern.

## 8. History and context boundary

Each scenario has raw-history sizes 1,3,5,…,19 at T1–T10 and **21 at T11**; latest-20 truncation crosses **only at T11** in all six. Raw window size is 20 there. Every saved turn has an empty ledger event list, including T11; no observed shift can be assigned to ledger injection. Current services/conversation_state.py can carry selected explicit corrections, rejections, and old boundaries, but that should not be projected backward as if the frozen run received them.

Before T11: 42/60 question endings and all 18 repetition flags. At T11: 0/6 questions and 0/6 repetition flags. Every T11 scripted user asks to stop or leave the matter, so the rate shift is confounded by closure. The strict T4–T6 loop and every first stall occur before truncation. **Latest-20 is not the primary explanation** for this defect, although it can create separate late-session loss that this run cannot measure.

## 9. Model-tendency evidence

**OBSERVED:** Frozen-prompt replication had 7/7 low-value questions on rich_reflection, after historical 10/12 on the same case. Saved response texts ask variants of what it means to keep cooking personal rather than work after reflecting the supplied distinction. Controlled A/B improved that target from 4/5 low-value baseline to 1/5 candidate, but introduced two low-value questions in emotional_answered, one over-suppressed useful-control answer, and three direct-request authorship concerns. Both arms still ended 28/40 responses in questions. answered_question_memory_analysis.md documents visible-answer/correction experiments where explicit already-answered metadata or a narrow instruction had little or inconsistent effect; one narrow prompt arm improved some samples without eliminating failure. The replication and A/B claims were checked against actual saved responses, not only reports.

**LIKELY:** The generator has a learned coaching prior to complete grounded reflection with an exploratory question, and the prompt does not consistently counter that prior outside “unknown” or explicit stop. The model *can* give question-free trajectories; it is not incapable of stopping. Prompt sensitivity and cross-case regressions make prompt structure and model tendency both relevant.

**UNPROVEN:** An intrinsic model prior independent of this prompt, a causal effect of the unloaded derived map, or superiority of another model. No neutral-prompt control or multi-turn response-mode A/B exists. The samples do not establish a population rate.

## 10. Local versus systemic causes

Confidence concerns this frozen defect, not all Olga conversations.

| Potential cause | Evidence for | Evidence against / limit | Confidence |
| --- | --- | --- | --- |
| Prompt asks too many questions | Explore/deepen/question wording makes inquiry available. | No mandate; anti-survey and optional sequence; uncertainty asks none. | LOW as literal claim |
| Prompt lacks strong no-question mode for ordinary clear turns | Loaded menu does not select when a complete reflection should end; 39 reflection-question turns; A/B shifts target. | Rich and uncertainty cases show no-question is possible. | HIGH contributor |
| Map overemphasizes progression | Nine stages and transition headings may shape designer framing. | Explicit pause/no-question/closure; unloaded. | LOW direct; MEDIUM indirect |
| Examples bias toward questions | Some consecutive question-only runs and tidy meaning checks. | 30/48 no-question; unloaded. | LOW direct |
| Model coaching prior | Wording variants after complete reflections; 7/7 replication; candidate redistributes modes. | No neutral-prompt/model-swap control; explicit cues can change behavior. | MEDIUM |
| History truncation | Can lose older details after T11. | Loops/stalls before boundary; T11 closure. | LOW |
| Conversation-state ledger | Could alter system message in other sessions. | Zero events in all 66 frozen turns. | LOW here |
| Evaluator incentives | Progression may reward inquiry during optimization. | Offline/post-generation; zero frozen calls; no-question allowed. | LOW generation; MEDIUM optimization |
| Scenario design | Fixed future turns, dense distinctions, T11 closure can expose/exaggerate cadence. | Redundancy is visible against prior user wording; useful questions also appear. | MEDIUM measurement effect |
| Manual-review bias | Utility and stall labels require judgment. | Exact text/mapping and replicated target make pattern inspectable. | MEDIUM uncertainty, not cause |

The strongest supported account is a **combination of loaded prompt response-mode imbalance and a model tendency toward familiar coaching continuation**. Derived conversation design contributes indirectly through an exploratory menu; the written map itself warns against the loop. Neither map nor synthetic examples are injected.

## 11. Interventions not justified now

- Generic “ask fewer questions”: would penalize useful identity T9/rich T5 and miss question-free reflection monotony.
- Generic appended “questions are optional” or another immediate wording tweak: tested candidate helped one fixture but regressed avoidance, useful clarification, and direct-request authorship; total question endings unchanged.
- More answered-question memory or larger ledger as *this* fix: repetition is visible before T11, all saved ledger blocks empty, prior visible-answer work shows salience alone is unreliable. Old-window recall is a separate problem.
- Semantic duplicate-question detector: generic continuation and premature action extend beyond paraphrases; semantic equivalence is risky and may block genuinely new inquiry.
- Global response post-processing to strip final questions: destroys useful clarifications and can leave awkward replies. Punctuation is not action choice.
- Lower question rate or evaluator rewards for silence as success: uncertainty is question-free yet sometimes merely mirrors; evaluators do not drive current runtime.

## 12. Four possible next intervention classes (no implementation)

| Class | Likely benefit | Regression risk | Complexity | Source fidelity | Testability | Prompt/token cost |
| --- | --- | --- | --- | --- | --- | --- |
| **A. Prompt rewrite/rebalance**: make reflection-only, clarification, question, acknowledgement peer choices based on current turn and trajectory, not another appended prohibition. | Best chance to correct clear-turn default while preserving useful inquiry. | Medium/high given previous cross-case regression; keep unknown/rejection/authorship controls. | Medium: prompt design plus frozen multi-turn and single-turn controls. | High if labeled derived response selection, not Olga verbatim technique. | High: compare functions and trajectories, not question rate alone. | Medium; replace/reorganize rather than only add text. |
| **B. Response-mode selector**: REFLECT, CLARIFY, EXPLORE, ANSWER, STOP before generation. | Could make trajectory-aware mode choice explicit. | High: wrong selection suppresses inquiry or forces action; model-assisted selection adds a fallible call. | High: new component, state/trace/fallback. | Medium: product operational rule, not directly Olga-sourced. | Medium/high, with added selector-error surface. | Deterministic: no recurrent prompt cost but code burden; model-assisted: call/tokens. |
| **C. Better canonical examples in runtime**, clearly synthetic. | Could teach sufficient reflection and concrete clarification. | Medium/high: overfit, provenance contamination, recurring token load. | Medium: curation, loading change, controls. | Medium only when explicitly synthetic/derived, never real Olga transcripts. | Medium via A/B on varied cases and guards. | High recurring system tokens. |
| **D. Accept tendency/defer** | Avoid immediate regressions. | Leaves real coherence weakness. | Low. | Preserves current implementation but no quality gain. | Easy monitoring. | Zero. |

## 13. Verdict and next action

**Primary verdict: MULTIPLE CAUSES — PROMPT/DESIGN COMBINATION.** The loaded prompt's safe-move menu and limited ordinary-turn mode-choice guidance leave reflection→inquiry attractive; the model likely supplies a learned coaching default. This does not say the unloaded map or examples directly drove the output. Counterexamples and useful questions rule out a blanket inability to stop asking.

**Next action: DESIGN A RESTRUCTURED RESPONSE-MODE PROMPT EXPERIMENT.** Design only, no implementation here. Rebalance existing instructions so acknowledgement, reflection, clarification, question, and stop are peer choices keyed to visible user material and trajectory, while preserving hard method boundaries. This is preferable to another appended rule because the completed appended candidate improved one target but shifted other contexts in the wrong direction while leaving total question endings unchanged. Success means the appropriate action for the turn and trajectory, including a useful question where needed, not a lower question rate.

Source check: inspected the four named method files, five loaded method files, four named implementation analyses, both evaluator specifications, harness/fixture, services/coaching_generator.py, services/conversation_state.py, handlers/chat.py, prompts/coaching.py, services/methods/loader.py, six frozen conversation JSON files plus frozen manifest/manual review/report, and saved replication/A-B manifests/reports/review data and actual sample responses. No runtime, fixture, method, example, evaluator, DB, or environment file was edited.
