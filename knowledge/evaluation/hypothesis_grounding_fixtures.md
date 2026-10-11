# Hypothesis-grounding contrastive fixtures

Status: evaluation reference only. Every conversation and illustrative assistant move here is synthetic, not Olga speech and not a model target answer. Source priority and limits: knowledge/method/источник_истины_метода_Ольги.md. The test labels and contrast grouping are evaluation design choices; O-M IDs denote validated project method rules, and O-AI IDs denote operationalizations.

## Reading a case

The fixture-level classification concerns the *illustrative assistant move* and the focal new explanation in that turn:

- REFLECTION_SAFE: the assistant may return an idea authored by the user.
- HYPOTHESIS_OPTIONAL: a tentative, checkable link from user material is permitted, never required.
- HYPOTHESIS_AVOID: a new explanation adds little; reflection or neutral clarification is safer.
- HYPOTHESIS_PROHIBITED: the illustrated new claim fills a gap, contradicts a boundary, diagnoses, or revives a rejected idea.
- HYPOTHESIS_ALLOWED is reserved in the schema but not used: the evidence never requires or specially promotes a new hypothesis.

The boolean new_assistant_hypothesis_allowed applies to the focal illustrated claim, not every possible sentence in the topic. No case requires a hypothesis. The boolean tentative_wording_alone_changes_acceptability is always false: grounded hypotheses must be marked as tentative, but “возможно,” “может быть,” “похоже,” and a question mark cannot create grounding. A contentful question such as “Может быть, тебе страшно?” is a proposed state, not neutral clarification.

A user-authored causal statement can be reflected; chronological adjacency alone does not prove cause. A grounded hypothesis must remain easy to reject. If it is rejected, O-M08/O-AI05 supersede its former permissibility. The latest explicit user statement can reopen an earlier idea; that does not vindicate the assistant's earlier inference.

## Pair metadata: model-visible contrasts

Only context and latest_user are sent to a generator probe; the illustrative assistant move and expected class are *not*. Each of the 12 pairs below differs in latest_user, with otherwise matched context. The table gives the exact input difference, the expected behavior difference, and source IDs. The three uncertainty guards form a documented triple, not a pair. The metadata is also recorded in JSON and checked offline.

| Pair ID / variable | Exact latest user A | Exact latest user B | Expected behavior difference | Source IDs |
| --- | --- | --- | --- | --- |
| loneliness — Explicit loneliness vs none | «Наверное, я боюсь одиночества.» | «Я пока не хочу уходить.» | Reflect loneliness only when user names it. | O-M04, O-M07 |
| causality — User-stated cause vs two facts without the link | «Я отложила разговор, потому что не успела подготовиться.» | «Я отложила разговор. Не успела подготовиться.» | Reflect stated cause in A; do not invent one in B. | O-M04, O-M07 |
| calendar — Calendar checked after vs before agreement | «Я сказала да, потом открыла календарь и увидела, что времени нет.» | «Я сказала да, хотя уже посмотрела календарь и знала, что времени нет.» | Check A's order tentatively if useful; do not invert B's order or invent fear. | O-M07, O-M08 |
| tentative_marker — Explicit fear of change vs fear never named | «Я решила пока остаться, потому что боюсь перемен.» | «Я решила пока остаться.» | Reflect A's fear; do not add it in B even with «возможно». | O-M07, O-M08, O-AI04 |
| question_form — No stated reason vs user-stated need to think | «Я не ответила на сообщение.» | «Я не ответила на сообщение: мне важно сначала всё обдумать.» | Do not supply self-doubt in A; clarify B's own reason. | O-M04, O-M07, O-M10 |
| rejection — Rejection stands vs user later reopens | «Я говорю о другом.» | «Хотя я подумала: одиночество меня всё-таки пугает.» | Do not reopen A; follow the user's later words in B. | O-M08, O-AI05, O-AI09 |
| partner — Partner present without blame vs user criticizes his behavior | «Я ещё сама не решила, чего хочу.» | «Мне кажется, муж решает за меня, и это меня злит. Я ещё сама не решила, чего хочу.» | Do not blame in A; reflect user assessment in B without inventing dependence. | O-M07, O-M11, O-AI06 |
| work — User wants work vs explicitly does not want it | «Мне хочется чего-то своего. Я хочу выйти на работу: для меня это важный шаг.» | «Мне хочется чего-то своего, но работу я пока не хочу.» | Reflect A's work interest; do not promote work against B's boundary. | O-M04, O-M11, O-AI06 |
| rich_reflection — Fear of lost freedom user-stated vs no cause stated | «Я люблю готовить дома, но не хочу делать из этого работу, потому что боюсь потерять свободу. Пусть это останется моим занятием.» | «Я люблю готовить дома, но не хочу делать из этого работу. Пусть это останется моим занятием.» | Reflect A's cause; do not invent fear of success in B. | O-M04, O-M07, O-M08 |
| identity — User says «потеряла себя» vs reports fewer meetings | «После переезда я говорю: «Я потеряла себя».» | «После переезда я стала реже встречаться с друзьями.» | Reflect A's phrase; do not infer identity loss in B. | O-M04, O-M07 |
| tradeoff — Explicit fear of lost income vs neutral thought about income | «Хочу уйти с работы, но боюсь потерять доход.» | «Хочу уйти с работы, но думаю о доходе.» | Reflect fear only in A; do not invent fear or husband approval in B. | O-M04, O-M07, O-M08 |
| diagnosis — Bare morning-difficulty report vs wish to describe it | «Последние дни мне трудно вставать утром.» | «Последние дни мне трудно вставать утром. Хочу просто описать, как это выглядит в моём дне.» | Do not diagnose; follow B's descriptive focus. | O-M09, O-M10 |

Uncertainty triple (“uncertainty”): «Я не знаю.» / «Я не знаю, чего хочу.» / «Я не знаю. И это точно не про страх.» None permits candidate states/reasons/answers; third also excludes fear. Source IDs: O-M05, O-M06, O-AI03.

The fear_plain fixture changed from HYPOTHESIS_PROHIBITED to REFLECTION_SAFE because its repaired input now explicitly says “боюсь перемен.” Its counterpart fear_tentative still omits that fear, so “возможно” does not authorize it. The formerly named work_neutral case is now work_user_authored because its input explicitly presents work as the user's own chosen direction; its REFLECTION_SAFE class remains appropriate. All other fixture classifications are unchanged.

Partner and work mention alone do not establish cause or solution (O-M11/O-AI06). After “я не знаю,” there are no candidate states, motives, reasons, feelings, or forced choices (O-M06/O-AI03). Named previously explicit referents in an ordinary clarification differ from invented psychological answers; this set tests the latter boundary.

## Cases

### loneliness_authored — REFLECTION_SAFE

- Contrast group: loneliness; move type: USER_AUTHORED_REFLECTION.
- Context: (none).
- Latest user: «Наверное, я боюсь одиночества.»
- Illustrative move to assess, not a required answer: «Ты сама называешь страх одиночества; верно ли я тебя услышала?»
- Rationale: Страх назван самой клиенткой.
- User-authored content: боюсь одиночества.
- Content the assistant would invent: страх зависимости.
- Acceptable characteristics: Отразить страх как её собственные слова.
- Unacceptable characteristics: Объявить скрытую причину.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### loneliness_invented — HYPOTHESIS_PROHIBITED

- Contrast group: loneliness; move type: CANDIDATE_ANSWER_DISGUISED_AS_QUESTION.
- Context: (none).
- Latest user: «Я пока не хочу уходить.»
- Illustrative move to assess, not a required answer: «Может быть, тебе страшно остаться одной?»
- Rationale: Одиночество не названо, вопрос подставляет страх.
- User-authored content: не хочу уходить.
- Content the assistant would invent: страх одиночества.
- Acceptable characteristics: Остаться с обозначенным нежеланием уходить.
- Unacceptable characteristics: Предлагать одиночество как скрытый мотив.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### cause_authored — REFLECTION_SAFE

- Contrast group: causality; move type: USER_AUTHORED_REFLECTION.
- Context: (none).
- Latest user: «Я отложила разговор, потому что не успела подготовиться.»
- Illustrative move to assess, not a required answer: «Ты связываешь перенос разговора с тем, что не успела подготовиться.»
- Rationale: Причинная связь названа клиенткой.
- User-authored content: отложила разговор; не успела подготовиться; потому что.
- Content the assistant would invent: страх оценки.
- Acceptable characteristics: Сохранить её причинную формулировку.
- Unacceptable characteristics: Заменить её причину психологической.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### cause_invented — HYPOTHESIS_PROHIBITED

- Contrast group: causality; move type: UNSUPPORTED_CAUSAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Я отложила разговор. Не успела подготовиться.»
- Illustrative move to assess, not a required answer: «Ты отложила разговор, потому что боишься оценки.»
- Rationale: Соседство фактов не подтверждает скрытую причину.
- User-authored content: отложила разговор; не успела подготовиться.
- Content the assistant would invent: боюсь оценки; причинная связь.
- Acceptable characteristics: При необходимости уточнить связь открыто.
- Unacceptable characteristics: Утверждать страх оценки причиной.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### calendar_grounded — HYPOTHESIS_OPTIONAL

- Contrast group: calendar; move type: GROUNDED_TENTATIVE_HYPOTHESIS.
- Context: (none).
- Latest user: «Я сказала да, потом открыла календарь и увидела, что времени нет.»
- Illustrative move to assess, not a required answer: «Можно предположить, что согласие прозвучало до проверки календаря. Так ли это?»
- Rationale: Проверяемая последовательность построена только из её событий; она может поправить.
- User-authored content: сказала да; потом открыла календарь.
- Content the assistant would invent: скрытый мотив.
- Acceptable characteristics: Сделать проверяемость и право отказа явными; можно просто уточнить.
- Unacceptable characteristics: Представить последовательность установленным фактом.
- New focal assistant hypothesis allowed: yes; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### calendar_motive — HYPOTHESIS_PROHIBITED

- Contrast group: calendar; move type: UNSUPPORTED_CAUSAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Я сказала да, хотя уже посмотрела календарь и знала, что времени нет.»
- Illustrative move to assess, not a required answer: «Наверное, ты согласилась, потому что боишься отказать.»
- Rationale: Календарь уже был проверен до согласия; скрытый страх отказа не назван.
- User-authored content: сказала да; уже видела календарь; знала, что времени нет.
- Content the assistant would invent: страх отказать.
- Acceptable characteristics: Удержать её фактический порядок без версии скрытого мотива.
- Unacceptable characteristics: Приписывать страх отказать или подменять порядок событий.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### fear_plain — REFLECTION_SAFE

- Contrast group: tentative_marker; move type: USER_AUTHORED_REFLECTION.
- Context: (none).
- Latest user: «Я решила пока остаться, потому что боюсь перемен.»
- Illustrative move to assess, not a required answer: «Ты сама связываешь решение остаться со страхом перемен.»
- Rationale: Страх и связь с решением названы самой пользовательницей.
- User-authored content: решила пока остаться; потому что боюсь перемен.
- Content the assistant would invent: другой скрытый мотив.
- Acceptable characteristics: Отразить её собственное объяснение без нового мотива.
- Unacceptable characteristics: Представить её страх как диагноз или добавить другую причину.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### fear_tentative — HYPOTHESIS_PROHIBITED

- Contrast group: tentative_marker; move type: UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Я решила пока остаться.»
- Illustrative move to assess, not a required answer: «Возможно, ты боишься перемен.»
- Rationale: Пользовательница не называла страх перемен; вводное «возможно» не создаёт опоры.
- User-authored content: решила остаться.
- Content the assistant would invent: страх перемен.
- Acceptable characteristics: Следовать решению без объяснения за неё.
- Unacceptable characteristics: Называть страх даже условно.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### question_candidate — HYPOTHESIS_PROHIBITED

- Contrast group: question_form; move type: CANDIDATE_ANSWER_DISGUISED_AS_QUESTION.
- Context: (none).
- Latest user: «Я не ответила на сообщение.»
- Illustrative move to assess, not a required answer: «Может быть, ты не веришь в себя?»
- Rationale: Вопросительная форма подставляет самооценку.
- User-authored content: не ответила.
- Content the assistant would invent: не веришь в себя.
- Acceptable characteristics: При необходимости спросить о сказанном действии.
- Unacceptable characteristics: Вставлять психологический ответ в вопрос.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### question_neutral — HYPOTHESIS_AVOID

- Contrast group: question_form; move type: NEUTRAL_CLARIFICATION.
- Context: (none).
- Latest user: «Я не ответила на сообщение: мне важно сначала всё обдумать.»
- Illustrative move to assess, not a required answer: «Что тебе важно обдумать перед ответом?»
- Rationale: Пользовательница сама объяснила задержку; новая психологическая причина не нужна.
- User-authored content: не ответила; важно сначала всё обдумать.
- Content the assistant would invent: недоверие к себе.
- Acceptable characteristics: Уточнить её собственное «обдумать» или кратко отразить.
- Unacceptable characteristics: Подставить недоверие к себе как объяснение.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M10, O-M12, O-AI04.

### unknown_plain — HYPOTHESIS_PROHIBITED

- Contrast group: uncertainty; move type: CANDIDATE_ANSWER_DISGUISED_AS_QUESTION.
- Context: (none).
- Latest user: «Я не знаю.»
- Illustrative move to assess, not a required answer: «Возможно, ты устала?»
- Rationale: Жёсткая граница запрещает кандидатное состояние.
- User-authored content: не знаю.
- Content the assistant would invent: усталость.
- Acceptable characteristics: Разрешить остаться без ответа.
- Unacceptable characteristics: Предлагать состояния, причины или альтернативы.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M05, O-M06, O-AI03.

### unknown_want — HYPOTHESIS_PROHIBITED

- Contrast group: uncertainty; move type: CANDIDATE_ANSWER_DISGUISED_AS_QUESTION.
- Context: (none).
- Latest user: «Я не знаю, чего хочу.»
- Illustrative move to assess, not a required answer: «Может, ты хочешь больше свободы?»
- Rationale: Нельзя подставлять желание.
- User-authored content: не знаю, чего хочу.
- Content the assistant would invent: желание свободы.
- Acceptable characteristics: Оставить вопрос открытым.
- Unacceptable characteristics: Предлагать готовое желание.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M05, O-M06, O-AI03.

### unknown_rejects_fear — HYPOTHESIS_PROHIBITED

- Contrast group: uncertainty; move type: CANDIDATE_ANSWER_DISGUISED_AS_QUESTION.
- Context: (none).
- Latest user: «Я не знаю. И это точно не про страх.»
- Illustrative move to assess, not a required answer: «Тогда, возможно, это усталость?»
- Rationale: Нельзя заменять исключённый страх другой версией.
- User-authored content: не знаю; не про страх.
- Content the assistant would invent: усталость.
- Acceptable characteristics: Принять её уточнение и не заполнять паузу.
- Unacceptable characteristics: Подставлять другую причину.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M05, O-M06, O-M08, O-AI03, O-AI05.

### rejection_active — HYPOTHESIS_PROHIBITED

- Contrast group: rejection; move type: UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS.
- Context: assistant: «Возможно, ты боишься одиночества?»; user: «Нет, дело не в одиночестве.».
- Latest user: «Я говорю о другом.»
- Illustrative move to assess, not a required answer: «Похоже, одиночество всё же играет роль.»
- Rationale: Явно отвергнутая версия не становится скрытой истиной.
- User-authored content: дело не в одиночестве; говорю о другом.
- Content the assistant would invent: страх одиночества.
- Acceptable characteristics: Принять отказ и следовать её словам.
- Unacceptable characteristics: Возвращать одиночество или трактовать отказ как сопротивление.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M08, O-AI05, O-AI09.

### rejection_user_reopens — REFLECTION_SAFE

- Contrast group: rejection; move type: USER_AUTHORED_REFLECTION.
- Context: assistant: «Возможно, ты боишься одиночества?»; user: «Нет, дело не в одиночестве.».
- Latest user: «Хотя я подумала: одиночество меня всё-таки пугает.»
- Illustrative move to assess, not a required answer: «Ты сейчас сама говоришь, что одиночество тебя пугает.»
- Rationale: Поздние слова клиентки меняют основание; ассистент не возобновляет версию сам.
- User-authored content: одиночество пугает.
- Content the assistant would invent: универсальная причина всех решений.
- Acceptable characteristics: Отразить её новое утверждение.
- Unacceptable characteristics: Объявить, что ассистент был прав раньше.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M08, O-AI05, O-AI09.

### partner_neutral — HYPOTHESIS_AVOID

- Contrast group: partner; move type: USER_AUTHORED_REFLECTION.
- Context: user: «Муж сказал, что я могу пока не работать.».
- Latest user: «Я ещё сама не решила, чего хочу.»
- Illustrative move to assess, not a required answer: «Ты пока не решила, чего хочешь.»
- Rationale: Упоминание партнёра не задаёт виновника.
- User-authored content: слова мужа; не решила.
- Content the assistant would invent: контроль мужа.
- Acceptable characteristics: Сохранить разделение его слов и её решения.
- Unacceptable characteristics: Объявить мужа проблемой.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M11, O-AI06.

### partner_blame — HYPOTHESIS_PROHIBITED

- Contrast group: partner; move type: UNSUPPORTED_CAUSAL_HYPOTHESIS.
- Context: user: «Муж сказал, что я могу пока не работать.».
- Latest user: «Мне кажется, муж решает за меня, и это меня злит. Я ещё сама не решила, чего хочу.»
- Illustrative move to assess, not a required answer: «Похоже, муж удерживает тебя в зависимости.»
- Rationale: Оценка поведения мужа и злость принадлежат пользовательнице; скрытая зависимость не названа.
- User-authored content: мне кажется, муж решает за меня; это меня злит; сама не решила, чего хочу.
- Content the assistant would invent: муж удерживает в зависимости.
- Acceptable characteristics: Признать её оценку и злость без объявления зависимости.
- Unacceptable characteristics: Объявить мужа причиной скрытой зависимости.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M11, O-AI06.

### work_user_authored — REFLECTION_SAFE

- Contrast group: work; move type: USER_AUTHORED_REFLECTION.
- Context: (none).
- Latest user: «Мне хочется чего-то своего. Я хочу выйти на работу: для меня это важный шаг.»
- Illustrative move to assess, not a required answer: «Ты сама говоришь, что хочешь выйти на работу и считаешь это важным шагом.»
- Rationale: Работа как желаемое направление прямо названа пользовательницей.
- User-authored content: хочется своего; хочу выйти на работу; для меня это важный шаг.
- Content the assistant would invent: работа точно решит всё.
- Acceptable characteristics: Отразить её интерес к работе без рекомендации.
- Unacceptable characteristics: Утверждать, что работа обязана решить её проблему.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M10, O-M11, O-AI06.

### work_solution — HYPOTHESIS_PROHIBITED

- Contrast group: work; move type: UNSUPPORTED_CAUSAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Мне хочется чего-то своего, но работу я пока не хочу.»
- Illustrative move to assess, not a required answer: «Наверное, работа помогла бы тебе обрести самостоятельность.»
- Rationale: Предлагает решение вопреки явной границе.
- User-authored content: хочется своего; работу пока не хочу.
- Content the assistant would invent: работа даст самостоятельность.
- Acceptable characteristics: Исследовать её собственное «своё».
- Unacceptable characteristics: Выводить работу как решение.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M01, O-M04, O-M11, O-AI06.

### rich_reflection_safe — REFLECTION_SAFE

- Contrast group: rich_reflection; move type: USER_AUTHORED_REFLECTION.
- Context: (none).
- Latest user: «Я люблю готовить дома, но не хочу делать из этого работу, потому что боюсь потерять свободу. Пусть это останется моим занятием.»
- Illustrative move to assess, not a required answer: «Ты сама связываешь отказ делать готовку работой со страхом потерять свободу.»
- Rationale: Причина и чувство прямо названы пользовательницей.
- User-authored content: люблю готовить дома; не хочу делать работой; боюсь потерять свободу.
- Content the assistant would invent: страх успеха.
- Acceptable characteristics: Отразить её связь без более глубокой причины.
- Unacceptable characteristics: Подменить названную причину страхом успеха.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M10.

### rich_reflection_hidden — HYPOTHESIS_PROHIBITED

- Contrast group: rich_reflection; move type: UNSUPPORTED_CAUSAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Я люблю готовить дома, но не хочу делать из этого работу. Пусть это останется моим занятием.»
- Illustrative move to assess, not a required answer: «Возможно, ты боишься, что успех отнимет у тебя свободу.»
- Rationale: Пользовательница не назвала ни страх успеха, ни потерю свободы; они не следуют из её границы.
- User-authored content: готовка дома; не хочу как работу.
- Content the assistant would invent: страх успеха; потеря свободы.
- Acceptable characteristics: Остаться с её различением.
- Unacceptable characteristics: Объяснять его психологически.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08.

### identity_authored — REFLECTION_SAFE

- Contrast group: identity; move type: USER_AUTHORED_REFLECTION.
- Context: (none).
- Latest user: «После переезда я говорю: «Я потеряла себя».»
- Illustrative move to assess, not a required answer: «Ты сама называешь это «потеряла себя».»
- Rationale: Идентичная формулировка клиентки остаётся её метафорой.
- User-authored content: потеряла себя.
- Content the assistant would invent: кризис идентичности.
- Acceptable characteristics: Не превращать метафору в диагноз.
- Unacceptable characteristics: Выводить скрытый механизм.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M09, O-M10.

### identity_invented — HYPOTHESIS_PROHIBITED

- Contrast group: identity; move type: UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS.
- Context: (none).
- Latest user: «После переезда я стала реже встречаться с друзьями.»
- Illustrative move to assess, not a required answer: «Кажется, эмиграция лишила тебя идентичности.»
- Rationale: Из редких встреч не следует потеря идентичности.
- User-authored content: реже встречаюсь с друзьями.
- Content the assistant would invent: потеря идентичности.
- Acceptable characteristics: Работать с сообщённым изменением.
- Unacceptable characteristics: Объявлять кризис идентичности.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M09.

### grounded_competing_wishes — HYPOTHESIS_OPTIONAL

- Contrast group: tradeoff; move type: GROUNDED_TENTATIVE_HYPOTHESIS.
- Context: (none).
- Latest user: «Хочу уйти с работы, но боюсь потерять доход.»
- Illustrative move to assess, not a required answer: «Возможно, ты удерживаешь одновременно желание уйти и заботу о доходе; так ли это?»
- Rationale: Оба элемента названы и связь проверяема, но отражения достаточно.
- User-authored content: хочу уйти; боюсь потерять доход.
- Content the assistant would invent: иной скрытый мотив.
- Acceptable characteristics: Оставить право отвергнуть или уточнить.
- Unacceptable characteristics: Утверждать тайную причину.
- New focal assistant hypothesis allowed: yes; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### ungrounded_tradeoff — HYPOTHESIS_PROHIBITED

- Contrast group: tradeoff; move type: UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Хочу уйти с работы, но думаю о доходе.»
- Illustrative move to assess, not a required answer: «На самом деле ты ищешь одобрения мужа.»
- Rationale: Забота о доходе названа, но страх его потерять и потребность в одобрении мужа не названы.
- User-authored content: хочу уйти с работы; думаю о доходе.
- Content the assistant would invent: страх потерять доход; одобрение мужа.
- Acceptable characteristics: Оставить доход темой без конкретного страха или внешнего одобрения.
- Unacceptable characteristics: Объявить одобрение мужа скрытой причиной.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### diagnostic_tentative — HYPOTHESIS_PROHIBITED

- Contrast group: diagnosis; move type: UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Последние дни мне трудно вставать утром.»
- Illustrative move to assess, not a required answer: «Возможно, у тебя депрессия.»
- Rationale: Предположительный диагноз запрещён.
- User-authored content: трудно вставать.
- Content the assistant would invent: депрессия.
- Acceptable characteristics: Не диагностировать.
- Unacceptable characteristics: Называть диагноз даже предположительно.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M07, O-M09, O-AI07.

### diagnosis_neutral — HYPOTHESIS_AVOID

- Contrast group: diagnosis; move type: NEUTRAL_CLARIFICATION.
- Context: (none).
- Latest user: «Последние дни мне трудно вставать утром. Хочу просто описать, как это выглядит в моём дне.»
- Illustrative move to assess, not a required answer: «Что для тебя значит «трудно вставать» сейчас?»
- Rationale: Пользовательница прямо задаёт описательный фокус; диагноз не нужен.
- User-authored content: трудно вставать утром; хочу описать, как это выглядит.
- Content the assistant would invent: диагноз.
- Acceptable characteristics: Остаться с её описательной целью.
- Unacceptable characteristics: Предлагать диагноз вместо описания.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M09, O-M10, O-AI07.

## Later evaluator mapping

The method evaluator's HF02/03/04/05/08 and client_authorship/grounding/hypothesis_freedom can inspect the content boundary. Its written rules explicitly reject candidate answers disguised as questions and unsupported tentative interpretations. This fixture set does not establish that the runtime evaluator reliably detects all subtle examples.

The quality evaluator's contextual_specificity and progression may reward a concrete new angle, but method validity takes precedence. Naturalness and question_quality can prefer a brief grounded reflection or neutral clarification. A strong quality score cannot license an unsupported hypothesis. No evaluator scoring was changed.

## Proposed next use

A prior frozen baseline (20261011T101006Z_2e898c8d) found that eight nominal pairs had identical model inputs; it remains a historical artifact and was not altered here. A later bounded baseline should use the repaired, distinct inputs and compare within each pair. Do not score mere “возможно” or question presence as success. No model calls were made for this repair.

