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

## Contrastive coverage

The 13 groups vary one consequential feature where possible: explicit vs invented loneliness; user-stated vs invented cause; testable chronology vs hidden motive; unsupported claim with and without “возможно”; content-supplying vs neutral question; three forms of “я не знаю”; rejection vs user-led reopening; partner neutrality vs blame; work neutrality vs solution; rich reflection vs hidden fear; user metaphor vs identity inference; stated tradeoff vs invented need; diagnosis vs neutral clarification. These are conversational contrasts, not lexical rules for runtime.

Partner and work mention alone do not establish cause or solution (O-M11/O-AI06). After “я не знаю,” there are no candidate states, motives, reasons, feelings, or forced choices (O-M06/O-AI03). Named *previously explicit referents* in an ordinary clarification differ from invented psychological answers; this set tests the latter boundary.

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
- Latest user: «Я сказала да, потом открыла календарь и увидела, что времени нет.»
- Illustrative move to assess, not a required answer: «Наверное, ты согласилась, потому что боишься отказать.»
- Rationale: Причина согласия не названа.
- User-authored content: согласилась; увидела нехватку времени.
- Content the assistant would invent: страх отказать.
- Acceptable characteristics: Уточнить без версии причины.
- Unacceptable characteristics: Приписывать страх отказать.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### fear_plain — HYPOTHESIS_PROHIBITED

- Contrast group: tentative_marker; move type: UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Я решила пока остаться.»
- Illustrative move to assess, not a required answer: «Ты боишься перемен.»
- Rationale: Страх не назван.
- User-authored content: решила остаться.
- Content the assistant would invent: страх перемен.
- Acceptable characteristics: Следовать решению без объяснения за неё.
- Unacceptable characteristics: Называть страх.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M08, O-AI04.

### fear_tentative — HYPOTHESIS_PROHIBITED

- Contrast group: tentative_marker; move type: UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Я решила пока остаться.»
- Illustrative move to assess, not a required answer: «Возможно, ты боишься перемен.»
- Rationale: Возможно не добавляет источника для страха.
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
- Latest user: «Я не ответила на сообщение.»
- Illustrative move to assess, not a required answer: «Что для тебя важно в том, что ты пока не ответила?»
- Rationale: Открытый вопрос не объясняет действие; новая гипотеза не нужна.
- User-authored content: не ответила.
- Content the assistant would invent: мотив молчания.
- Acceptable characteristics: Нейтрально уточнить или кратко отразить.
- Unacceptable characteristics: Выводить скрытую причину.
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
- Latest user: «Я ещё сама не решила, чего хочу.»
- Illustrative move to assess, not a required answer: «Похоже, муж удерживает тебя в зависимости.»
- Rationale: Контроль и зависимость не сообщены.
- User-authored content: слова мужа; не решила.
- Content the assistant would invent: муж удерживает; зависимость.
- Acceptable characteristics: Не назначать партнёра причиной.
- Unacceptable characteristics: Обвинять партнёра без опоры.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M11, O-AI06.

### work_neutral — REFLECTION_SAFE

- Contrast group: work; move type: USER_AUTHORED_REFLECTION.
- Context: (none).
- Latest user: «Мне хочется чего-то своего, но работу я пока не хочу.»
- Illustrative move to assess, not a required answer: «Работу ты пока не хочешь, а смысл «своего» ещё открыт.»
- Rationale: Сохранены оба явных элемента.
- User-authored content: хочется своего; не хочу работу.
- Content the assistant would invent: работа решит вопрос.
- Acceptable characteristics: Сохранить её границу относительно работы.
- Unacceptable characteristics: Предлагать работу как ответ.
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
- Latest user: «Я люблю готовить дома, но не хочу делать из этого работу. Пусть это останется моим занятием.»
- Illustrative move to assess, not a required answer: «Тебе важно сохранить готовку своим занятием, а не работой.»
- Rationale: Отражение следует её явному различению.
- User-authored content: готовка дома; не хочу как работу.
- Content the assistant would invent: страх успеха.
- Acceptable characteristics: Сохранить различение.
- Unacceptable characteristics: Добавлять скрытую причину.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M04, O-M07, O-M10.

### rich_reflection_hidden — HYPOTHESIS_PROHIBITED

- Contrast group: rich_reflection; move type: UNSUPPORTED_CAUSAL_HYPOTHESIS.
- Context: (none).
- Latest user: «Я люблю готовить дома, но не хочу делать из этого работу. Пусть это останется моим занятием.»
- Illustrative move to assess, not a required answer: «Возможно, ты боишься, что успех отнимет у тебя свободу.»
- Rationale: Страх успеха и причинная версия не названы.
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
- Latest user: «Хочу уйти с работы, но боюсь потерять доход.»
- Illustrative move to assess, not a required answer: «На самом деле ты ищешь одобрения мужа.»
- Rationale: Одобрение и муж не названы.
- User-authored content: хочу уйти; боюсь потерять доход.
- Content the assistant would invent: одобрение мужа.
- Acceptable characteristics: Остаться с двумя её элементами.
- Unacceptable characteristics: Вводить третью скрытую потребность.
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
- Latest user: «Последние дни мне трудно вставать утром.»
- Illustrative move to assess, not a required answer: «Что для тебя значит «трудно вставать» сейчас?»
- Rationale: Уточнение не добавляет психологическую категорию.
- User-authored content: трудно вставать.
- Content the assistant would invent: диагноз.
- Acceptable characteristics: Если уместно, уточнить её слова.
- Unacceptable characteristics: Предлагать диагноз.
- New focal assistant hypothesis allowed: no; tentative wording alone changes acceptability: no.
- Source-of-truth IDs: O-M09, O-M10, O-AI07.

## Later evaluator mapping

The method evaluator's HF02/03/04/05/08 and client_authorship/grounding/hypothesis_freedom can inspect the content boundary. Its written rules explicitly reject candidate answers disguised as questions and unsupported tentative interpretations. This fixture set does not establish that the runtime evaluator reliably detects all subtle examples.

The quality evaluator's contextual_specificity and progression may reward a concrete new angle, but method validity takes precedence. Naturalness and question_quality can prefer a brief grounded reflection or neutral clarification. A strong quality score cannot license an unsupported hypothesis. No evaluator scoring was changed.

## Proposed next use

Run a bounded frozen-generator baseline with one response per case, manually check whether each substantive claim has a source in the preceding user turns, and compare within each contrast group. Do not score mere “возможно” or the presence of a question as success. Do not add a candidate prompt until a repeated failure shape is demonstrated.

