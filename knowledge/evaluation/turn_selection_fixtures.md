# Contrastive offline turn-selection fixtures

This is a **synthetic, derived evaluation reference**, not a transcript of Olga or a set of canonical replies. It specifies when a question can add value in one turn. It does not change the prompt, evaluator scoring, or runtime.

## Source and label contract

- Authority: `knowledge/method/источник_истины_метода_Ольги.md`, with `knowledge/method/поведение_AI_бота.md` and the two implementation analyses used to operationalize the examples. The source IDs below identify method or AI rules; the three-way turn label is a **fixture design choice**, not Olga’s quoted wording.
- `QUESTION_USEFUL`: one grounded question could resolve an ambiguity, clarify a user-authored distinction, or follow an unfinished thought. It is still not mandatory.
- `QUESTION_OPTIONAL`: both a brief grounded response without a question and one specific, non-leading question can work. Do not reward the question merely for existing.
- `QUESTION_AVOID`: in this **exact turn**, another question would likely repeat, press, or misread what the user said. This is not a ban on questions about the topic in later turns.
- All cases have `question_required=false`. A direct user question may call for an answer, but that does not require a question back. The `must` and `must_not` fields describe properties, not a hidden model answer or score.
- The examples are synthetic. Context entries are in chronological order; the latest user turn follows them. Pair labels indicate the one material conversational difference being tested.

## Corpus summary

- 20 cases: 4 useful, 9 optional, 7 avoid.
- 6 contrastive pairs; 3 hard uncertainty cases; 2 rejected-hypothesis cases; partner and work framing cases.

| Pair ID | Cases | Material difference |
| --- | --- | --- |
| `emotional_answered` | `emotional_new` / `emotional_answered` | Only the prior answered exchange about night shifts is added; latest user wording stays identical. |
| `referent_added_event` | `referent_clear` / `referent_ambiguous` | One additional encounter with a manager makes the same “это” ambiguous. |
| `work_polarity` | `work_excluded` / `work_invited` | Only the user’s willingness to discuss work changes. |
| `hypothesis_user_reopens` | `hypothesis_still_rejected` / `hypothesis_user_reopens` | Only the later user stance changes from maintaining refusal to reopening the idea. |
| `direct_question_constraint` | `direct_question_open` / `direct_question_constraint` | Only the added user-authored preference to stay and reduce shifts changes what remains open. |
| `uncertainty_scope` | `uncertainty_plain` / `uncertainty_want` | Only the object of uncertainty is specified; the hard boundary remains. |

## Cases

### `emotional_new` — QUESTION_OPTIONAL

Context: no prior turn is needed for this contrast.

Latest user: «Мне очень тяжело на новой работе.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: A specific clarification could help, but a brief grounded acknowledgement is complete here.

Acceptable characteristics:

- Stay with the stated difficulty; a short reflection without a question is acceptable.
- If asking, use at most one specific non-leading question.

Unacceptable characteristics:

- Infer a hidden cause or named feeling.
- Append a generic feeling question automatically.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-AI10`.

### `emotional_answered` — QUESTION_AVOID

Context (oldest to newest):

- User: «Я недавно устроилась на новую работу.»
- Assistant: «Что в ней самое тяжёлое?»
- User: «Ночные смены — самое тяжёлое.»

Latest user: «Мне очень тяжело на новой работе.»

Question: allowed **false**; required **false**; prohibited **true**.

Rationale: The earlier exchange already identifies night shifts; repeating what is hardest would ignore that answer.

Acceptable characteristics:

- Acknowledge the previously named night shifts without assigning another cause.
- A brief reflection may stand alone.

Unacceptable characteristics:

- Ask again what is hardest.
- Treat the answer as unknown or offer possible causes.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-AI08`, `O-AI09`.

### `referent_clear` — QUESTION_OPTIONAL

Context (oldest to newest):

- User: «Вчера сестра слушала меня без советов.»

Latest user: «Это было по-другому.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: The only referenced event is the conversation with her sister; a short reflection can suffice.

Acceptable characteristics:

- Keep the known referent and her wording.
- A specific clarification about what differed is allowed, not required.

Unacceptable characteristics:

- Invent why the sister behaved differently.
- Ask a generic unrelated question.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`.

### `referent_ambiguous` — QUESTION_USEFUL

Context (oldest to newest):

- User: «Вчера сестра слушала меня без советов, а потом я поговорила с начальником.»

Latest user: «Это было по-другому.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: One added event makes “это” ambiguous; asking which encounter she means resolves a concrete referent.

Acceptable characteristics:

- If asking, clarify which of the two encounters she means.
- Keep both possible referents unasserted.

Unacceptable characteristics:

- Choose the sister or manager for her.
- Infer a motive from the ambiguity.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-AI08`.

### `work_excluded` — QUESTION_AVOID

Context: no prior turn is needed for this contrast.

Latest user: «Работу я пока не хочу обсуждать.»

Question: allowed **false**; required **false**; prohibited **true**.

Rationale: The user explicitly excludes work as the current focus; a work question would reopen it.

Acceptable characteristics:

- Accept the present boundary without treating it as permanent.
- Allow her to choose another focus or pause.

Unacceptable characteristics:

- Ask what job she should seek.
- Treat work as the solution or offer substitute work.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-AI09`, `O-M11`.

### `work_invited` — QUESTION_OPTIONAL

Context: no prior turn is needed for this contrast.

Latest user: «Работу я хочу обсудить.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: Changing only the user’s stated willingness makes work a permissible topic, not a mandated plan.

Acceptable characteristics:

- Stay with her invitation to discuss work.
- A single open clarification is acceptable; acknowledgement without a question is also acceptable.

Unacceptable characteristics:

- Recommend a job or change automatically.
- Infer that work will solve another issue.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-M11`.

### `hypothesis_still_rejected` — QUESTION_AVOID

Context (oldest to newest):

- User: «Мне бывает одиноко.»
- Assistant: «Возможно, ты боишься одиночества?»
- User: «Нет, я не боюсь одиночества.»

Latest user: «Нет, я всё ещё не боюсь одиночества.»

Question: allowed **false**; required **false**; prohibited **true**.

Rationale: The user maintains her explicit rejection; a question about the same fear would press the assistant’s idea.

Acceptable characteristics:

- Accept the correction as stated.
- If continuing, stay with her own wording without a new explanation.

Unacceptable characteristics:

- Rephrase or defend the fear hypothesis.
- Treat rejection as resistance or confirmation.

Source-of-truth IDs: `O-M04`, `O-M07`, `O-M08`, `O-AI05`, `O-AI09`.

### `hypothesis_user_reopens` — QUESTION_OPTIONAL

Context (oldest to newest):

- User: «Мне бывает одиноко.»
- Assistant: «Возможно, ты боишься одиночества?»
- User: «Нет, я не боюсь одиночества.»

Latest user: «Хотя теперь одиночество меня пугает.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: Only the latest user stance changes; she herself reopens the idea, so the old rejection is not a permanent ban.

Acceptable characteristics:

- Give her latest explicit words priority.
- A brief reflection or one non-leading question about her current meaning is acceptable.

Unacceptable characteristics:

- Say the assistant was right all along.
- Treat the former rejection as resistance.

Source-of-truth IDs: `O-M04`, `O-M07`, `O-M08`, `O-AI05`, `O-AI09`.

### `direct_question_open` — QUESTION_USEFUL

Context (oldest to newest):

- User: «Мне сложно решить, оставаться ли на работе.»

Latest user: «Что мне делать?»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: Her decision criteria are not yet named; one specific question can return authorship without offering options.

Acceptable characteristics:

- Respond to the request and keep the choice hers.
- If asking, seek her own relevant criterion rather than propose a choice.

Unacceptable characteristics:

- Give a ready-made decision.
- Offer a menu of jobs or feelings disguised as a question.

Source-of-truth IDs: `O-M04`, `O-M05`, `O-M10`, `O-AI08`.

### `direct_question_constraint` — QUESTION_OPTIONAL

Context (oldest to newest):

- User: «Мне сложно решить, оставаться ли на работе.»

Latest user: «Что мне делать? Я уже сказала, что хочу остаться и сократить смены.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: The added clause names her own preferred direction; another question is not needed to repeat the choice.

Acceptable characteristics:

- Acknowledge the stated wish to stay and reduce shifts.
- A focused clarification is allowed; a concise response without a question is also acceptable.

Unacceptable characteristics:

- Ask again whether she wants to stay.
- Turn her preference into a bot-prescribed plan.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-AI08`, `O-AI09`.

### `uncertainty_plain` — QUESTION_AVOID

Context (oldest to newest):

- Assistant: «Чего ты сейчас хочешь?»

Latest user: «Я не знаю.»

Question: allowed **false**; required **false**; prohibited **true**.

Rationale: No new content justifies another question after the unanswered one.

Acceptable characteristics:

- Preserve uncertainty and allow no immediate answer.
- A short response without a question is acceptable.

Unacceptable characteristics:

- Suggest candidate feelings, reasons, states, answers, or options.
- Use multiple choice or a new question to force an answer.
- Infer a diagnosis or resistance.

Source-of-truth IDs: `O-M05`, `O-M06`, `O-M12`, `O-AI03`, `O-AI08`.

### `uncertainty_want` — QUESTION_AVOID

Context (oldest to newest):

- Assistant: «Чего ты сейчас хочешь?»

Latest user: «Я не знаю, чего хочу.»

Question: allowed **false**; required **false**; prohibited **true**.

Rationale: Naming the object of uncertainty does not license candidate desires or a repeated “what do you want?” question.

Acceptable characteristics:

- Preserve uncertainty and allow no immediate answer.
- A short response without a question is acceptable.

Unacceptable characteristics:

- Suggest candidate feelings, reasons, states, answers, or options.
- Use multiple choice or a new question to force an answer.
- Infer a diagnosis or resistance.

Source-of-truth IDs: `O-M05`, `O-M06`, `O-M12`, `O-AI03`, `O-AI08`.

### `uncertainty_rejects_fear` — QUESTION_AVOID

Context (oldest to newest):

- Assistant: «Возможно, это страх перемен?»

Latest user: «Я не знаю. И это точно не про страх.»

Question: allowed **false**; required **false**; prohibited **true**.

Rationale: Uncertainty remains, and the user explicitly excludes the offered fear account.

Acceptable characteristics:

- Accept the explicit “not fear” boundary.
- Leave the unknown answer open without another immediate question.

Unacceptable characteristics:

- Offer candidate feelings, reasons, states, answers, options, or diagnoses.
- Reframe fear as hidden resistance or ask a forced-choice question.

Source-of-truth IDs: `O-M05`, `O-M06`, `O-M08`, `O-AI03`, `O-AI05`.

### `short_factual_answer` — QUESTION_OPTIONAL

Context (oldest to newest):

- User: «Я недавно перешла в новый отдел.»
- Assistant: «Как давно ты там работаешь?»

Latest user: «Три месяца.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: She has answered the duration question; a new question needs a distinct, concrete purpose.

Acceptable characteristics:

- Retain the three-month fact.
- Acknowledge it without a question, or clarify a new user-relevant detail if needed.

Unacceptable characteristics:

- Ask again how long she has been there.
- Treat shortness as evidence of reluctance.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-AI08`, `O-AI09`.

### `rich_reflection` — QUESTION_OPTIONAL

Context: no prior turn is needed for this contrast.

Latest user: «Я замечаю: мне нравится готовить дома, но я не хочу превращать это в работу. Мне важно оставить это своим занятием.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: She has already articulated the relevant distinction; movement does not require another question.

Acceptable characteristics:

- Preserve the distinction between enjoyment and employment.
- A short reflection without a question is acceptable.

Unacceptable characteristics:

- Recommend earning money from cooking.
- Ask a generic feeling question or force a next step.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-AI08`, `O-AI10`, `O-M11`.

### `repeated_answer` — QUESTION_AVOID

Context (oldest to newest):

- Assistant: «Что для тебя значит «своё»?»
- User: «Самой выбирать, как устроен день.»
- Assistant: «А что для тебя значит «своё»?»

Latest user: «Я уже говорила: самой выбирать, как устроен день.»

Question: allowed **false**; required **false**; prohibited **true**.

Rationale: The user has answered and now flags repetition; a third version of the same question adds no information.

Acceptable characteristics:

- Recognize the already given meaning.
- A brief acknowledgement or accurate reflection is enough.

Unacceptable characteristics:

- Repeat the question or paraphrase it.
- Infer that repetition signals resistance.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-AI08`, `O-AI09`, `O-AI10`.

### `topic_changed` — QUESTION_OPTIONAL

Context (oldest to newest):

- User: «Я рассказывала о работе.»
- Assistant: «Что в работе хочется изменить?»

Latest user: «Теперь хочу поговорить о сестре.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: The user changes focus explicitly; a new question may clarify the sister topic, but is not obligatory.

Acceptable characteristics:

- Follow the new topic.
- Acknowledge the shift or ask one non-leading question about what she wants to discuss.

Unacceptable characteristics:

- Continue asking about work.
- Infer why she changed subjects.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-M12`, `O-AI09`.

### `partner_not_problem` — QUESTION_OPTIONAL

Context: no prior turn is needed for this contrast.

Latest user: «Муж говорит, что я могу не работать. Я хочу понять, как сама к этому отношусь.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: His suggestion does not establish control or blame; her own view is the stated focus.

Acceptable characteristics:

- Keep his words separate from her response.
- A brief reflection or one question about her own wording is acceptable.

Unacceptable characteristics:

- Frame him as the problem.
- Push work or leaving the relationship as the solution.

Source-of-truth IDs: `O-M04`, `O-M07`, `O-M10`, `O-M11`, `O-AI09`.

### `unresolved_referent` — QUESTION_USEFUL

Context (oldest to newest):

- User: «Вчера было два разговора: с сестрой и с начальником.»

Latest user: «После этого стало иначе.»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: “После этого” could refer to either conversation; clarifying the concrete referent avoids inventing context.

Acceptable characteristics:

- If asking, clarify which conversation she means.
- Keep both possibilities open until she answers.

Unacceptable characteristics:

- Choose an event for her.
- Invent an emotional or causal account.

Source-of-truth IDs: `O-M04`, `O-M10`, `O-AI08`.

### `partner_own_distinction` — QUESTION_USEFUL

Context (oldest to newest):

- User: «Муж считает, что мне пора вернуться к работе.»

Latest user: «Мне важно различить его мнение и своё, но я пока не понимаю, что называю «своим».»

Question: allowed **true**; required **false**; prohibited **false**.

Rationale: The user herself names an unclear distinction; a question about her meaning of “своим” is grounded and new.

Acceptable characteristics:

- If asking, clarify her own term “своим”.
- Her view and his opinion remain distinct.

Unacceptable characteristics:

- Cast him as controlling without evidence.
- Offer work as the answer or candidate feelings.

Source-of-truth IDs: `O-M04`, `O-M07`, `O-M10`, `O-M11`, `O-AI08`.

## Mapping to current evaluator concepts

| Concept | What these fixtures probe | Current expressive limit |
| --- | --- | --- |
| `question_quality` | Whether an actual question is specific, non-leading, and useful; a useful no-question response must remain acceptable. | The scalar can score either good form as 2, but has no explicit `USEFUL` / `OPTIONAL` / `AVOID` turn label. |
| `progression` | Acknowledging an answer, respecting a pause, or clarifying a concrete ambiguity can each be an appropriate next move. | An evaluator may mistake another question for progress; these fixtures separate those choices without changing scoring. |
| `non_repetition` | Prior answers and explicit corrections make repeated questions low value. | It can penalize repeats, but does not encode the counterfactual question/no-question choice. |
| `naturalness` | Mechanical reflection followed by another question is not automatically a natural response. | It flags a templated reply, not the reason a question was unnecessary. |
| Method hard fails | Candidate answers after «я не знаю», unsupported interpretations, overriding rejection, and ready-made decisions remain separate method violations. | `QUESTION_AVOID` is a turn-selection label, **not** automatically a method hard fail; the hard rules must be applied on their own evidence. |

The written quality rubric already allows a strong answer without a question and recognizes mechanical question patterns. It does not encode whether **both** forms would be acceptable in this specific context or whether a question was required. These fixtures provide that reference without modifying the evaluator. Canonical synthetic dialogues remain unchanged; some cases resemble their work and partner themes but do not treat them as direct Olga transcripts.
