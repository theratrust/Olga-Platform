# Olga Coaching DEV product readiness audit

Scope: static/offline inspection of feature/method-core and its existing tests, 12 October 2026. No Telegram, provider, running DEV database, or PROD access. The coaching-behavior work (referents, hypotheses, uncertainty, already-answered memory, response mode, and multi-turn prompt design) remains frozen. The six-scenario multi-turn harness remains a regression benchmark; its known verdict is single-turn quality good, multi-turn coherence weak. This report evaluates the **product journey**, not a fresh model sample. Configuration-sensitive claims distinguish the DEV_DIRECT_CHAT direct path from the moderated path; .env.dev and running container configuration were not opened, so the active setting is unverified.

## Executive answer

A first-time user can follow the happy path from /start through a three-question quiz and enter coaching. Once in AI_CHAT, private text and transcribed voice share session-scoped history and generation. **The journey is not end-to-end ready for a returning user after process restart:** bot.py uses MemoryStorage, there is no FSM rehydration, and chat.py silently discards a text turn unless AI_CHAT is present. The quiz result is stored only in FSM despite unused database fields. Old quiz callbacks also lack a current-question/message check. These are product continuity and quiz-integrity blockers; no prompt change is indicated.

## Readiness table

Every LIMITED/BLOCKING row names the concrete failure, user impact, static reproduction, component, fix category, and rough scope. “Reproduce” describes an offline/code-supported path, not a live Telegram action.

| Area | Status | Exact failure and user impact | Reproduction path | Likely component | Fix kind / scope |
| --- | --- | --- | --- | --- | --- |
| First start | LIMITED | Welcome assumes relocation was “продиктован любовью” and offers only a quiz button; a target user with a different reason is misframed and cannot see another entry choice. DEV image lookup can fall through to a PROD image path if local images are absent; actual fallback use was not checked. | /start; read caption/button and bot.py:get_image_file search order. | handlers/start.py; bot.py | UX / SMALL; environment isolation / SMALL |
| Onboarding | BLOCKING | Quiz/AI_CHAT state is process-memory only. Interruption or restart loses position; ordinary text sent outside AI_CHAT gets no guidance. No back/cancel/restore path is registered. | /start → one answer → restart or lose FSM → send text or old quiz callback. | bot.py MemoryStorage; handlers/quiz.py; handlers/chat.py | persistence + UX / MEDIUM |
| Quiz | BLOCKING | Three-answer score and result are FSM-only; database users.test_result/answers are never written by this path. q_ans callbacks are not state- or message-bound, allowing an old/duplicate button to score against the current index; wrong result is possible. | Finish quiz, lose FSM; or invoke a retained q_ans_ option after another question is current. | handlers/quiz.py; database.py unused profile helpers | persistence + behavioral integrity / MEDIUM |
| Quiz→coaching | LIMITED | Result is sent, then after a delay “👉 Задать вопрос” opens AI_CHAT; copy does not explain that quiz result is optional context and is lost on restart. Stale open_ai_chat is ungated, so it can enter coaching without a completed quiz. | Result → open_ai_chat; or use an earlier button after FSM loss. | handlers/quiz.py; handlers/callbacks.py; handlers/chat.py | UX + behavioral / MEDIUM |
| Returning user | BLOCKING | DB session/history survive, but absent FSM means text is silently ignored; no startup rehydration or resume instruction. Genuine quiz result also disappears. | Complete coaching → process restart/FSM loss → send text. | bot.py MemoryStorage; handlers/chat.py state gate; handlers/callbacks.py | persistence + UX / MEDIUM |
| Text coaching | LIMITED | Happy path is coherent, but pre-generation acknowledgement can be followed by silent stale suppression; DB/read errors before the generation try have no user-facing recovery. Empty/nontext output has no dedicated retry. | AI_CHAT text → /new overtakes generation; or inject history/admission failure; or model returns blank content. | handlers/chat.py; services/coaching_generator.py | reliability / MEDIUM |
| Voice | LIMITED | Telegram voice and audio are accepted without format/size guard; both are uploaded with default filename voice.ogg. Download exceptions are uncaught. Transcription happens even outside AI_CHAT, then the coaching handler silently returns; user gets no transcript preview. | Send audio while quiz/in absent FSM; or inject get_file/download exception; or submit non-OGG audio. | handlers/voice.py; services/transcription.py; handlers/chat.py | UX + reliability / MEDIUM |
| /new | LIMITED | Reset rotates ID and deletes history/pending drafts, but a known post-reset update overtaking case can admit a valid later turn to the old conversation before /new runs, then delete it. The user may see an acknowledgement with no answer. | Offline handler order 103 normal before 102 /new, as in test_conversation_admission and post_new_overtaking_analysis. | handlers/chat.py; database.py admission/reset | architecture / LARGE; **LIMITED BUT ACCEPTABLE FOR DEV**, not production-ready |
| Private-chat boundary | READY | Private chat/user-ID check covers /start, /new, text, end-user voice, quiz and coaching callbacks. Admin voice's group behavior is a separate control path. | Static handler guards and existing private/group tests. | services/conversation_admission.py and handlers | No fix indicated |
| Moderation | LIMITED | When DEV_DIRECT_CHAT is false, user receives acknowledgement and waits for admin draft action with no clear pending status; rejection sends no user message. Approval/edit sends before persistence, so a post-send DB/session failure can leave a delivered reply absent from history. | AI_CHAT text under moderated configuration → reject, or inject save failure after user send. | handlers/chat.py; handlers/admin.py; database.py | UX + reliability / MEDIUM |
| Provider failure | LIMITED | Explicit finish_reason=length retries once; second failure gives a generic error while the user turn remains stored. Blank/nontext output is not retried as truncation. User may retry and create another user turn. | Inject length then length/error; inject empty response. | services/coaching_generator.py; handlers/chat.py | reliability + UX / MEDIUM |
| Persistence | BLOCKING | Conversation ID/rows are durable but quiz result, progress, and AI_CHAT eligibility are not. users table has fields but no quiz registration/update call; DB history alone cannot restore UI state. | Complete quiz/coaching → lose MemoryStorage → inspect available DB/FSM reads. | bot.py; handlers/quiz.py; handlers/chat.py; database.py | persistence / MEDIUM |
| User-facing copy | LIMITED | Welcome presumes motive; “👉 Задать вопрос” frames coaching as questions though statements are supported; result text implies a consolidated interpretation from three answers; no advertised /new/resume/voice guidance. | Read /start, result, buttons, coaching entry and /new copy. | handlers/start.py, quiz.py, callbacks.py, chat.py | UX / SMALL |
| Diagnostics | LIMITED | Safe operation/retry/stale logs exist, but no durable privacy-safe per-turn correlation, quiz-state transition trail, or default generator diagnostic observer wired into chat. Support cannot reliably explain “quiz disappeared” or tie a reported half-answer to finish_reason. | Inspect handler logs and generate_candidate observer default; no live logs used. | handlers/*; services/generator_diagnostics.py | reliability/supportability / MEDIUM |

## 1–4. Entry, onboarding, quiz, and handoff

/start is private-only, clears the current FSM (including a genuine in-memory quiz result and AI_CHAT), caches first name, and sends a photo/caption with one “Пройти экспресс-тест (2 мин)” button. It neither registers a user DB row nor rotates the existing conversation. The opening says the bot provides space to hear oneself but leads only to adaptation testing; it does not explain coaching without the quiz, voice, return behavior, or /new. The relocation/partner motive is asserted before the user supplies it. No back, cancel, or resume command appears in the registered quiz path. Sending plain text during the quiz is not routed to a helpful quiz response: the general text handler checks AI_CHAT and returns.

start_quiz deletes the welcome message if possible; it initializes default three questions, index 0, score 0, first name, and answer list in FSM, then sets QUESTION_STEP. Each q_ans_i callback acknowledges, waits two seconds, parses the index, reads the **current** FSM question, adds that option's 0/1/2 score and selected text, advances index, deletes the prior message if possible, and renders the next. After question 3 it sends a completion message/button and sets CALC. show_result is CALC-gated, reads total from FSM, maps 0 → “Свет”, 1–3 → “Полутень”, 4–6 → “Тень”, stores archetype only in FSM, sends result photo, waits five seconds, then sends “👉 Задать вопрос” and “👉 Узнать больше”. No database.register_user, update_user_test_result, or get_user_profile call is wired into this path. The DB columns do not imply usable persisted quiz context. A fresh quiz result can be used by chat.py only while FSM survives; no invented “Полутень” fallback exists in current chat.py.

Callback integrity is weaker than the happy-path score formula: q_ans_i is not constrained to QUESTION_STEP and does not verify callback.message.message_id against last_question_message_id. A retained old keyboard, duplicate delivery, or near-simultaneous callbacks can apply an option index to the wrong current question. It calls callback.answer before late invalid/index alerts. show_result is CALC-gated but likewise not tied to the current completion message; stale result buttons while CALC could show the current completed score from a different quiz instance. If deletion of the welcome message fails, start_quiz enters an exception handler that calls logging.exception without importing logging; that NameError aborts quiz start. start_quiz and open_ai_chat are private-only but have no “fresh current button” check. A stale open_ai_chat button can set AI_CHAT after restart or /start, bypassing the quiz. That makes quiz optional **in fact**, but not clearly an intentional product choice. /new also sets AI_CHAT without a quiz. The post-result copy does not explain that archetype is limited context subordinate to the user's words.

## 5. Text coaching and session behavior

Private non-command text in AI_CHAT passes original chat/message marker validation, then a short per-user admission lock. database.admit_user_message atomically gets/creates active_chat_sessions, checks the /new cutoff, and stores the user turn under its conversation ID. chat.py sends typing, builds the system instruction from real FSM archetype or None, loads up to the latest 20 ordered scoped rows, derives up to four source-linked ledger events from all current-session rows (or falls back to raw history on ledger-read failure), and calls the generator. Explicit provider length gets one retry with identical messages. Direct mode sends the generated reply and then conditionally stores the assistant row; moderated mode stores a draft instead. Shadow evaluators run after this path and do not change delivery.

The fixed “Спасибо, [name]! Я скоро напишу тебе...” message is one waiting acknowledgement per admitted text/voice turn, not a duplicate generated answer; tests confirm it no longer assumes every statement is a question. It can still confuse when a stale generation is discarded after /new: acknowledgement was sent, no further answer. If a DB exception occurs in admission, history or prompt assembly before the try around generation, the handler has no local user-facing error. If sending succeeds but conditional assistant save fails/raises, the user may receive the answer and then a generic error (or have missing history). The existing /new race is documented rather than redesigned here.

## 6. Voice

The handler accepts Telegram F.voice or F.audio; it checks private source for end users, downloads Telegram file bytes, sends typing, then calls OpenRouter-compatible whisper-1 transcription through services/transcription.py. It uses default filename voice.ogg for both kinds and does not inspect the actual filename/MIME, size, or duration. Transcription exceptions are logged and converted to empty text, yielding “❌ Не удалось распознать голосовое сообщение.” Telegram get_file/download errors are outside that catch and have no handler-specific reply. A successful transcript is assigned to message.text and passed to the same ai_chat_handler with the original message marker, so admission, legitimate FSM quiz context, session history, generator, retry, and persistence match text. No transcript confirmation is shown. Because transcription precedes the AI_CHAT gate, voice during quiz or after restart consumes a transcription attempt and then produces no coaching response. Admin voice is intentionally separate and outside the end-user policy.

## 7. /new

Private /new atomically rotates the active conversation ID and cutoff, deletes **all chat_messages for that user** and that user's PENDING drafts, then sets FSM AI_CHAT and shadow_conversation_id. It replies “Начинаем новый разговор. Предыдущая история очищена. Напиши, что сейчас для тебя важно.” The FSM archetype survives /new in the same process; quiz result is neither persisted nor recovered later. User profile fields and nonpending draft status rows survive; current-session history and ledger inputs do not. The DB cutoff and conditional writes prevent older generation/drafts from entering the new history; stale responses are silently suppressed after the waiting acknowledgement. The known handler-overtaking valid-turn loss remains. User-facing classification: **LIMITED BUT ACCEPTABLE FOR DEV** with documented race; this is not a claim of production readiness.

## 8. Returning-user cases

| Case | Recovered context / visible outcome |
| --- | --- |
| A. Several hours, process/FSM intact | AI_CHAT and archetype remain in MemoryStorage; DB session ID/history remain. User can continue. No TTL is configured in this storage path. |
| B. Process restart | MemoryStorage loses AI_CHAT, quiz position/result, and name cache. DB session ID and rows survive, but ordinary text/voice does not reach admission because AI_CHAT is absent. User receives no resume instruction. |
| C. FSM absent, DB history exists | Same silent gate. DB get_or_create_conversation_id could return identity, but the chat handler never calls it to rehydrate state; it is passed into register_chat but unused there. |
| D. Quiz completed previously | No quiz result is written to DB by quiz handler; only surviving FSM can supply archetype. A previously populated users.test_result from some outside path is not read into coaching. |
| E. Previous /new | Current DB ID/cutoff persist; prior history and pending drafts were deleted. After restart, AI_CHAT and archetype are still lost. |
| F. >20 messages | Chat resumes with latest 20 scoped rows *if FSM exists*. Full same-session rows feed deterministic carry-forward; qualifying explicit corrections/rejections/old boundaries may be injected under a four-item cap. General old dialogue is not recalled. |

Using /start after restart reopens the quiz but **does not clear the DB conversation**. Thus finishing it and opening AI_CHAT may resume the old coaching history while the user experienced a new welcome; /new is required to erase history, but is not advertised in the flow. This is a concrete expectation mismatch, not a prompt defect.

## 9. Error paths

| Path | Actual behavior |
| --- | --- |
| Provider/model exception | Caught around generation; user sees “Произошла ошибка связи. Попробуй написать ещё раз.” The admitted user turn remains in DB; no assistant turn is saved. |
| Explicit finish_reason=length then success | First candidate rejected by ExplicitTruncationError; one retry; only accepted second reply sent/saved or drafted. Covered by tests. |
| Second truncation or retry failure | Generic error; no direct answer or moderated draft. User turn remains. |
| Empty/None/nontext content without length | generate_candidate returns raw content; no dedicated validity guard/retry in direct coaching. Telegram send/draft path may fail or store unusable content. Exact provider/UI outcome depends on returned type and Telegram behavior. |
| Transcription API failure/empty text | services/transcription.py returns empty; user sees the voice-recognition failure copy. Telegram file retrieval/download failure is uncaught here. |
| DB failure | Admission, history and reset DB failures are not translated into a user message by these handlers; transaction rollback is implemented in DB operations. A ledger read failure alone falls back to recent history and logs a warning. |
| Malformed callback | q_ans parsing uses int without a catch; malformed q_ans_* can raise. Admin approve_/edit_/reject_ likewise parse int without a catch. Unmatched callbacks have no shown fallback. A welcome-message delete failure triggers missing logging import and aborts start_quiz. |
| Stale quiz callback | q_ans can act on current idx despite old message; if idx already past end it shows a late alert after an initial acknowledgement. show_result has CALC state gate; open_ai_chat has no state/freshness gate. |

## 10–11. Private boundary and moderation

services/conversation_admission.py requires private chat type and matching chat/user ID; a positive original message ID is required for coaching admission and /new. /start, /new, text, end-user voice, quiz callbacks, menu callbacks, and open_ai_chat all check private identity. Existing tests exercise group rejection. Admin voice in groups remains an explicit separate exception; it does not open end-user coaching.

DEV_DIRECT_CHAT is environment-configurable, default false in bot.py; active .env.dev value was deliberately not read. In moderated mode, the same generation/history/quiz context creates a persistent PENDING draft. Admin receives source message and generated reply plus approve/edit/reject buttons. Approval or edit checks current session, sends to the user, then atomically writes assistant history and draft status; a late reset can still occur between send and save. Rejection marks REJECTED and updates the admin message but sends **nothing** to the user, who has only the earlier waiting acknowledgement. Pending drafts are deleted by /new; stale nonpending rows remain. No real admin account was used.

## 12. Data and persistence map

| Data | Class | Location / recovery |
| --- | --- | --- |
| Users, optional test_result and answers columns | PERSISTENT schema | SQLite users table; helper functions exist but start/quiz/chat do not call them, so normal quiz flow does not populate/retrieve result. |
| User/assistant chat turns | PERSISTENT | SQLite chat_messages with conversation_id, scoped by user + active conversation; /new deletes user's rows. Moderation writes assistant only upon approve/edit. |
| Active conversation ID and /new cutoff | PERSISTENT | SQLite active_chat_sessions; survives process restart. |
| Pending/admin drafts | PERSISTENT | SQLite pending_drafts; /new deletes PENDING; approved/rejected status rows can remain. |
| Quiz question index, answers, score, archetype, name | PROCESS/FSM ONLY | aiogram MemoryStorage; lost on restart or state.clear at /start. |
| AI_CHAT/QUESTION_STEP/CALC eligibility; admin editing state | PROCESS/FSM ONLY | aiogram MemoryStorage; absent FSM prevents ordinary coaching despite durable DB history. |
| shadow_conversation_id cache | PROCESS/FSM ONLY | Observer cache refreshed from admitted DB ID, not session authority. |
| Latest-20 raw history, carry-forward ledger, prompt session context | DERIVED AT RUNTIME | DB reads + deterministic services/conversation_state.py; up to four event objects; no separate ledger table. |
| Transcribed voice text | PERSISTENT only after admission | Successful transcript becomes a normal user chat row; raw audio is downloaded in memory, not stored by this code. |

## 13. Concrete copy issues

- /start asserts a partner/love reason before asking: “Особенно когда этот шаг продиктован любовью и желанием быть рядом с близким человеком.” The user's actual motive may differ.
- “Пройти экспресс-тест (2 мин)” is the sole first button, while the product also supports coaching; no direct coaching or return path is explained.
- Result preamble “Я соединила все твои ответы в единую картину” can overstate what three scored choices establish. The archetype is optional context in coaching, not a diagnosis or durable profile.
- “👉 Задать вопрос” is narrower than actual coaching, which accepts statements, uncertainty, and voice transcripts. The neutral waiting acknowledgement is correctly worded now.
- /new copy says history is cleared, which is true for DB chat rows, but does not say quiz result remains in current FSM and vanishes after restart. No flow introduces /new, voice, or how to resume.
- menu_learn_more copy makes general causal assertions about adaptation and inner perception (for example “Твой мир вокруг — это зеркало твоих ежедневных мыслей о себе”) without user grounding. This is fixed product copy, not a model output; it merits source/UX review before presenting it as an explanation to a particular user.

## 14. Privacy-safe supportability

| User report | Available evidence | Gap |
| --- | --- | --- |
| “The bot forgot me” | DB conversation rows/ID could be examined in an authorized diagnostic context; safe stale/ledger event-type logs exist. | No durable FSM transition or resume reason; no per-turn correlation. Do not inspect a real user's DB in this audit. |
| “It stopped halfway” | Explicit truncation retry and generic error-kind logs; generator_diagnostics.py can project safe finish_reason/content length when an observer is supplied. | Chat does not supply that optional observer; no default linkage of provider finish to user turn or delivery. |
| “It asked the same thing” | Current scoped history and deterministic ledger source IDs exist; frozen multi-turn harness is a benchmark. | No privacy-safe per-turn response-mode trace or production trajectory diagnostic; avoid logging raw coaching text. |
| “My quiz disappeared” | Code proves MemoryStorage and no quiz DB write. | No persisted quiz completion/score provenance or restart event tied to a user report. |
| “/new behaved strangely” | Stale/rejection operation logs and durable cutoff; offline race tests. | No request correlation across acknowledgement, reset, generation and send; overtaking can be diagnosed only with careful event reconstruction. |

No logging expansion is proposed in this audit. Existing scalar/event logs are preferable to raw user text, but are not sufficient for all five support questions.

## 15. Existing test coverage by journey

| Journey | Coverage | Evidence and gap |
| --- | --- | --- |
| Private/group entry and coaching admission | GOOD COVERAGE for boundary | tests/test_conversation_admission.py exercises /start, quiz callbacks, text, voice, /new private/group rejection and original marker. It does not judge copy or first-run guidance. |
| First-run onboarding and quiz scoring/callback lifecycle | NO COVERAGE end-to-end | No test drives /start → all three q_ans → CALC → show_result → open_ai_chat, stale button, restart, or DB quiz persistence. Private boundary only is tested. |
| Quiz result in generator while FSM survives | PARTIAL | tests/test_conversation_state.py tests actual FSM archetype versus absent fallback; no process-loss/return restore path. |
| Text generation/session scoping and /new | GOOD COVERAGE for core mechanics | tests/test_conversation_sessions.py, test_conversation_admission.py, test_conversation_state.py cover scoped history, deletion, stale writes, explicit retry; known overtaking loss is codified, not solved. |
| Voice to text coaching | PARTIAL | test_conversation_admission.py tests private/group routing, original marker and neutral acknowledgement; no real file-format, download, transcription-service, or out-of-state UX journey. |
| Provider failure and explicit truncation | GOOD COVERAGE for length/retry; PARTIAL for all output shapes | test_generator_diagnostics.py and test_conversation_admission.py cover finish_reason=length, second failure, provider exception. Empty/nontext direct-chat UX lacks a complete journey test. |
| Moderation approve/edit/reject and stale session | PARTIAL | test_conversation_sessions.py and test_conversation_admission.py cover draft/session guards and retry; no full user-visible waiting/reject notification or send-before-save failure journey. |
| Returning user after restart/FSM loss | NO COVERAGE as product journey | DB ID survival is tested, but text/voice recovery with fresh MemoryStorage is not. |
| Multi-turn coaching behavior | GOOD COVERAGE as frozen regression artifact, not product gate | Six stateful scripted scenarios and 66 saved turns; known weak coherence is documented, not reopened here. |

Validation: pytest -q tests completed **999 passed in 28.17s**. This is strong module/regression coverage, not evidence that the full target-user journey survives a process restart.

## Priority: only three product blockers

Ranked by real-user exposure, likelihood, severity, fix confidence, then regression risk.

1. **Returning-user lockout after restart/FSM loss.** Normal deployments restart; durable conversation exists but AI_CHAT eligibility is gone and messages get no response. High severity and clear code evidence. First implementation slice should define an explicit, source-safe resume path and test it across fresh MemoryStorage, without changing conversation-state architecture or DB schema in this audit.
2. **Quiz result/progress not persisted or recoverable.** A genuine result disappears; the same user can resume old conversation without the context she just saw. The users table already has result fields but normal handlers do not use them. Decide product persistence semantics and qualify restoration after restart and /new before writing code.
3. **Stale/duplicate quiz callbacks can corrupt score or bypass quiz.** q_ans_i uses current index without callback state/message identity, and open_ai_chat is ungated. This affects the first-run path and can produce an apparently authoritative wrong result. Validate callback freshness/idempotency and intended quiz optionality in a bounded offline journey test.

These three are separate from the accepted DEV /new race limitation and from frozen coaching-response quality work. No broad backlog or prompt optimization is recommended.

## Three areas already good enough

1. **Private end-user boundary:** consistent guard across entry, quiz, coaching, reset and voice; admin path is separate.
2. **Core session-scoped text path:** admission, latest-20 history, optional deterministic ledger, active-ID checks, and reset fencing have meaningful offline tests.
3. **Provider-declared truncation guard:** one retry before delivery/persistence, generic failure after a second failure, and focused regression tests. No truncation investigation is needed here.

## Recommended next implementation slice (not implemented)

Design and test **return/resume behavior using a fresh in-memory FSM against an isolated test DB**, including prior quiz completion, prior /new, and a user turn after restart. Specify exactly when a stored quiz result is legitimate and when an old button may be accepted. Then implement the smallest bounded product fix under a separate authorization. Do not change coaching prompt, response-mode selection, conversation-state architecture, or schema as part of this audit.
