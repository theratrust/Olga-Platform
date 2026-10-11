# Questioning and reflect-then-ask: source-grounded audit

Status: analysis only, 11 October 2026. No prompt, runtime, test, evaluator, scenario, dialogue, or database changes. Static source and stored historical artifacts can show instructions, examples, and aggregate scores; they cannot establish the current generator's response-form frequency without candidate text. No live model calls were made.

## Authority and rule traceability

`knowledge/method/источник_истины_метода_Ольги.md` reports no independently verifiable primary Olga interview or real Olga dialogue in the repository. “Directly supported” below means directly supported by the **available project method rules**, not an authenticated direct Olga quotation. The eight dialogue examples are explicitly synthetic.

| IDs | Available rule | Status of proposed behavior |
| --- | --- | --- |
| O-M04, O-M10 | Follow the client's authorship, words, and topic; do not impose a frame. | **Directly supported:** a question must be grounded in what the client has said. |
| O-M05–06, O-AI03 | Preserve uncertainty, especially «я не знаю»; do not insert possible states/answers, even as a question. | **Directly supported** project boundary; a no-question response can be apt. |
| O-M12 | A question, reflection, hypothesis, or plan is not required every turn. | **Directly supported** as a derived method rule; not a fixed turn formula. |
| O-AI08 | Notice what was already answered; do not ask for form's sake. | **Necessary operationalization** of O-M04–05/O-M10–12. |
| O-AI09 | Use verifiable history and current user words first. | **Design choice** for deciding whether a question repeats an answer. |
| O-AI10 | Speak naturally; avoid a mechanical reflection then generic question. | **Design choice** grounded in O-M10–12 and style documents, not a personal Olga script. |

`поведение_AI_бота.md` §§7–9,18 explicitly says a question may be omitted when an answer is already present, the client has corrected the bot, a short acknowledgement suffices, or a question would exist only to keep the conversation going. `карта_коучингового_разговора.md` §Сквозные границы and final history rules say the same. These are source-supported permissions to stay with the user's words, **not** a mandate to answer with silence or never ask.

## Current generator and prompt path

`handlers/chat.py` saves the inbound user turn, loads the latest 20 scoped DB messages, optionally adds the deterministic boundary/rejection runtime block, and calls `build_messages`/`generate_candidate` from `services/coaching_generator.py`. Text and transcribed voice share the chat generator path; moderated drafts use the same candidate. The generator receives one system message plus chronological raw history, with `max_tokens=350`. `services/conversation_state.py` carries selected boundaries/corrections and rejected hypotheses, not a general answered-question inventory. No runtime function chooses “question vs acknowledgement vs reflection”, adds a closing question, or post-processes the generated response. The fixed pre-generation acknowledgement is neutral and separate from the candidate.

`prompts/coaching.py` builds the base prompt and loads `метод_Ольги.md`, `принципы.md`, `границы.md`, `паттерны.md`, and `язык_и_стиль.md` through `services/methods/loader.py`. The conversation map, AI-behavior specification, and synthetic dialogues are **not loaded into generator context**. The relevant prompt wording is:

| Short fragment | Classification | Effect/risk |
| --- | --- | --- |
| “помочь ему лучше услышать себя и прийти к собственному ответу” | Broad goal; derived implementation wording | Could be read as encouraging motion, but does not require a question. |
| “ты можешь: … отразить … уточнить … углубить” | Explicit optional menu | A reflection or clarification is permitted, not a required sequence. The loaded method core likewise offers patterns rather than a mandatory sequence. |
| “Это возможные рабочие ходы, а не обязательная последовательность” | Explicit nonrequirement | Directly counters a fixed reflect-then-ask routine. |
| “Вопрос должен помогать … собственную тему”; “Не превращай разговор в анкету” | Hard conditional constraint on questions | Forbids question-shaped interpretation and a series of questions; says nothing requiring a question. |
| “оставляй пространство” after «я не знаю» | Hard uncertainty boundary | Candidate states or multiple choice remain prohibited even if phrased as a question. |

No “always end with a question”, mandatory “move forward”, or mandatory “one question” directive exists in the generator prompt. The optional verbs may influence a model's style, but source inspection cannot show that they **cause** a recurrent output pattern. The prior `source_of_truth_gap_audit.md` F12/F15 also labels actual question habits unverified and warns that prompt-only attempts previously regressed other behavior.

## Eight synthetic dialogues: complete turn-structure count

Coding rule: classify the **assistant text only**, one exclusive primary form per turn. A = grounded reflection/summary with no question; B = question only (a quoted user phrase inside the question does not make a separate reflection); C = declarative reflection followed by a question; D = assistant hypothesis/interpretation followed by a question; E = acknowledgement followed by a question; F = other no-question move (permission, boundary, acceptance, invitation, or closure). This is a descriptive coding decision, not an Olga method taxonomy. Turn numbers below are the six `Обмен` sections in each synthetic dialogue.

| Dialogue | Turns 1–6 | A | B | C | D | E | F | End in `?` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1. Relocation / lost self | B B F B B F | 0 | 4 | 0 | 0 | 0 | 2 | 4 |
| 2. Work / “something of my own” | B F B A B F | 1 | 3 | 0 | 0 | 0 | 2 | 3 |
| 3. Husband / work | B A F C B A | 2 | 2 | 1 | 0 | 0 | 1 | 3 |
| 4. “I don't know what I want” | F F F C F F | 0 | 0 | 1 | 0 | 0 | 5 | 1 |
| 5. Repeated “I don't know” | F F F F A F | 1 | 0 | 0 | 0 | 0 | 5 | 0 |
| 6. Understand but do not change | B B D F F F | 0 | 2 | 0 | 1 | 0 | 3 | 3 |
| 7. Stuck without action | B B A F F F | 1 | 2 | 0 | 0 | 0 | 3 | 2 |
| 8. Closing without action plan | B A B A F F | 2 | 2 | 0 | 0 | 0 | 2 | 2 |
| **Total** | **48 turns** | **7** | **15** | **2** | **1** | **0** | **23** | **18 (37.5%)** |

Same-turn **reflection → question is 2/48** (dialogues 3 and 4), plus one hypothesis → question (dialogue 6). The examples therefore do **not** predominantly teach reflect-then-ask. However, dialogue 1 asks in turns 1–2 and again 4–5; dialogue 6 asks in turns 1–3. Those early runs can feel like an interview if copied as a cadence. Dialogue 6's turn 3 hypothesis largely restates the user's chronology, as the existing gap audit notes. Dialogues 4–5 explicitly model staying with uncertainty, including 0/6 questions in dialogue 5. Other no-question boundary/summary/closing turns appear in every dialogue. These examples are not loaded at runtime, so they are an illustration/possible future content influence, not a proven runtime cause. No canonical edit is justified by this count alone.

## Evaluator and stored-artifact findings

`knowledge/evaluation/метод_Ольги_оценка.md` says not to demand a hypothesis, question, or fixed sequence to award a good method score. Its hard rules prohibit candidate answers after «я не знаю» and unsupported interpretations; it does not reward question frequency. `knowledge/evaluation/качество_ответов_оценка.md` awards `question_quality=2` to a useful answer **without** a question, and says a short pause can count as strong `progression`. The quality corpus `tests/response_quality_evaluator_cases.json` labels `specific_grounded_reflection` and `no_question_useful` as strong with `progression=2, question_quality=2`; it labels a repeated “Что ты замечаешь?” structure weak with Q03/Q05. Thus the **written evaluator does not require questions**.

A softer measurement incentive remains: `progression` rewards a useful new distinction or next investigative step, and Q04 marks low progression. A model evaluator might mistake “another question” for movement or mark a well-judged pause as stagnant. That is a qualification risk, not established actual scoring bias. `naturalness`, `non_repetition`, Q03, and Q05 counter rote reflect-then-ask. The method and quality observers in `handlers/chat.py` run **after** candidate delivery/draft creation, receive the raw history, and cannot change the generated reply. Quality scores cannot override method hard fails by specification.

Existing historical conversation-benchmark JSON reports retain **hashes and aggregate scores, not candidate text** (`services/conversation_benchmark.py`; `services/quality_evaluation/CONVERSATION_BENCHMARK.md`). One 5 October six-scenario report has 30 valid generated/quality turns, 14 Q03 repetitive-structure flags and 4 Q05 generic-question flags; another has 27 valid turns, 8 Q03 and 3 Q05. The runs have different prompt hashes and precede current changes. These numbers suggest a style-quality concern in historical experiments but do **not** give a question-ending rate, prove “Ты говоришь … Что для тебя …?”, or establish current-model behavior. Stored evaluator-qualification cases contain *synthetic candidate fixtures*, not generator outputs. The six frozen benchmark scenarios use scripted user turns; they do not adapt to assistant questions, so they cannot by themselves prove a question was already answered. Actual current reflect-then-ask frequency and repeated-answer rate remain **UNVERIFIED** from available stored evidence.

## Narrow operational distinction

A **useful question** connects to a specific new phrase, event, or ambiguity in the latest user turn; opens something the user has not already answered; supplies no candidate answer; and is not added merely because a response seems incomplete without a question. A **low-value continuation question** repeats an answered inquiry, asks generically what the user feels/wants despite adequate context, follows a reflection by habit, or exists only to keep the exchange moving. One question may be useful; no question may also be a complete turn. A concise acknowledgement must not assign an emotion or close the conversation against the user's wishes.

## Options and smallest next slice

| Option | Likely benefit | Regression/qualification risk | Decision now |
| --- | --- | --- | --- |
| A. Add “Не обязательно заканчивать каждый ответ вопросом” | Very small, reminds model of an existing method permission. | Prompt already says turns are optional and forbids an interview; prior prompt-only candidates had broader regressions. Could suppress helpful questions without diagnosing current behavior. | Defer. |
| B. “Ask only when it adds value” | States the right criterion. | Vague without examples; close to existing “Вопрос должен помогать…” wording. | Too little new information. |
| C. Correct synthetic dialogues only | Could soften dialogue 1/6 early question streaks if reused as examples. | They are not loaded by the generator; editing them cannot directly fix current runtime. Most turns already show no-question options. | Not the first fix. |
| D. Adjust quality evaluator | Could ensure a good pause never loses `progression`. | Written rubric and fixtures already allow this; changing scoring before measuring judgement bias may mask genuine stagnation. Shadow evaluation is nonblocking. | Defer. |
| E. Narrow prompt line plus contrastive fixtures | Direct runtime intervention with offline regression evidence. | Adds an instruction where no current output-rate failure is proven; prior prompt trials regressed. | Conditional later experiment only. |

**Recommended first implementation slice: an offline, contrastive turn-selection qualification fixture set using existing synthetic scenarios and current generator input assembly, with no live call or runtime/prompt/evaluator change in that slice.** Record human source-grounded expectations for “question useful/optional/avoid” and candidate no-question vs generic-question replies; include prior-turn answer context and the hard «я не знаю» boundary. The fixture should test the quality rubric's existing no-question expectations and define a future paired comparison if model calls are separately authorized. This is a small, reversible **test/content design choice**. The current system already permits reflection or acknowledgement without a question. There is insufficient evidence here to justify a prompt change as the next code edit; if a qualified paired sample later confirms an excessive pattern, test **one** narrow line against the unchanged baseline and broader regression suite before retaining it.

## Offline fixture matrix (no model calls)

The labels apply to the specified context, not to all utterances of the same type.

| # | Synthetic context/last user turn | Question status | Source-grounded contrast to encode |
| --- | --- | --- | --- |
| 1 | Clear emotional statement: “Мне тяжело на новой работе”; no request for analysis. | **Optional** only for a specific unresolved detail; a brief grounded acknowledgement can suffice. | Penalize an invented feeling/reason plus generic “что чувствуешь?”. |
| 2 | User has just answered the assistant's question about whether work matters. | **Avoid** repeating it. | Acknowledge the answer; do not reopen as an equivalent question. |
| 3 | “Я не знаю” after a question asking what she wants. | **Avoid** an immediate new candidate-answer question. | A short no-question response can be strong; no feelings, reasons, options, or multiple choice. |
| 4 | Short factual answer to a specific prior question, with no new ambiguity. | **Optional** only if a fresh user-relevant detail needs clarification. | Do not mechanically append another question. |
| 5 | Direct “Что мне делать?” with named constraints. | **Useful** if it asks about her own criterion without offering a choice; a grounded no-question response remains possible. | No ready decision or menu of options. |
| 6 | User explicitly rejects the assistant's interpretation. | **Avoid** a new explanation-seeking question that defends/replaces it. | Accept correction and follow her wording; no “resistance” inference. |
| 7 | Rich reflective paragraph already articulating the distinction she sees. | **Optional**. | Specific brief reflection may stand alone; do not ask her to repeat the distinction. |
| 8 | User repeats herself after the same assistant question appeared twice. | **Avoid** that question or paraphrase. | Recognize repetition without claiming a hidden reason. |
| 9 | User explicitly changes topic. | **Optional** if the new topic's meaning is unclear. | Follow the new words; no automatic return to previous topic. |
| 10 | User says “Это было по-другому” with no clear referent in visible history. | **Useful** clarifying question. | Ask what “это” refers to, without supplying candidate interpretations. |

## Conclusion and risks

The **demonstrated** issue is a measurement/selection gap: the runtime has no response-form selector, while the written method already permits no-question turns; some synthetic early sequences are question-heavy, and historical aggregate flags show repetitive/generic-question weaknesses without raw text. There is **no demonstrated current-model reflect-then-ask rate or single causal prompt line**. Treat a prompt edit as conditional, not automatically necessary.

Top five risks for the next slice: (1) labeling a useful clarification as unwanted; (2) treating a short generic acknowledgement as adequate when it ignores a direct question; (3) rewarding silence or premature closure after «я не знаю»; (4) mistaking aggregate Q03/Q05 flags for actual question frequency or using old prompt variants as current evidence; (5) using synthetic fixed-turn dialogues as authoritative Olga cadence or as proof of live behavior.
