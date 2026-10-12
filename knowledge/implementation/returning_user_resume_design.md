# Returning-user resume after MemoryStorage loss: offline design and proof

Status: design and current-behavior characterization only, feature/method-core. No runtime handler, prompt, schema, configuration, running database, Telegram, or model change. This document uses the current source, not the earlier readiness audit as authority. The new tests execute real registered handler functions against disposable SQLite and fake Telegram/provider ports. The host pytest environment has no aiogram package, so the tests use a deliberately fresh MemoryStorage-equivalent FSM double; bot.py itself wires aiogram MemoryStorage. This proves the handler/DB decision boundary, not aiogram's internal implementation.

## 1. Current state contract

| Fact | Current authority/class | Exact evidence and limit |
| --- | --- | --- |
| User exists | PERSISTENT_DB only if users row is independently registered; otherwise NOT_REPRESENTED in that table | database.py defines users and register_user, but no normal /start, quiz, callback, or chat call to register_user. A chat user may have session/history without users row. Telegram from_user exists only in the current update. |
| Onboarding started | FSM_ONLY | /start clears FSM and stores user_first_name; start_quiz puts questions/index/score/answers into FSM. No durable started marker. |
| Quiz completed | FSM_ONLY / DERIVED while process lives | After three answers, render_question_step sets CALC; show_result calculates from FSM total and stores archetype in FSM. No durable completion timestamp or source linkage. |
| Quiz result | FSM_ONLY in normal path; PERSISTENT_DB field exists but unused | users.test_result and users.answers columns plus update_user_test_result helper exist, but quiz handler never calls registration/update and chat never reads profile. Legacy values in those fields have unknown provenance. |
| Coaching eligibility | FSM_ONLY | callbacks.enter_chat sets AI_CHAT; /new also sets AI_CHAT; chat.ai_chat_handler requires that exact state before DB admission. No durable eligibility bit. open_ai_chat currently has no quiz-completion guard, which is a current-path weakness, not proof that DB implies onboarding. |
| Active conversation_id | PERSISTENT_DB | active_chat_sessions keyed by user_id; admission creates it when needed, /new rotates it. get_or_create_conversation_id would create a row and must not be used as a read-only eligibility probe. |
| Prior chat history | PERSISTENT_DB | chat_messages role/content rows carry user_id and conversation_id; generator sees latest 20 for current ID; ledger derives from current ID's full rows. History is content evidence, not onboarding evidence. |
| /new state | PERSISTENT_DB for new ID/cutoff/deletions; FSM_ONLY for AI_CHAT/cache | rotate_conversation atomically writes current ID plus cutoff_chat_id/message_id, deletes user chat rows and PENDING drafts; cmd_new sets AI_CHAT and shadow_conversation_id only in memory. It leaves FSM archetype in the same process. |
| Moderation pending | PERSISTENT_DB | pending_drafts stores source user, candidate, status, conversation_id; approval/edit checks active ID. Admin editing state is separate FSM_ONLY state. A pending draft does not prove quiz or coaching eligibility. |

Schema/migration verification: init_db creates users, chat_messages, pending_drafts, active_chat_sessions, adds conversation_id to legacy message/draft tables, adds cutoff columns to old active-session tables, and indexes scoped history. It does **not** add onboarding/coaching fields. Neither a users row, active_chat_sessions row, pending draft, nor history row has a provenance flag for normal quiz completion or coaching entry. The unused quiz columns look intended for result/answers, but current code neither populates nor consumes them. No psychological inference is relevant to recovery.

Startup wiring: bot.py constructs Dispatcher(storage=MemoryStorage()) and Quiz states QUESTION_STEP, CALC, AI_CHAT; it registers /start, callbacks, quiz, chat, and voice. There is no DB-to-FSM rehydration at startup or on a new update. /start clears FSM without rotating DB conversation.

## 2. Offline fresh-memory characterization (tests/test_returning_user_resume.py)

The five passing test functions cover the required six current cases, using a real three-question normal quiz path, result callback, coaching-entry callback, one generated exchange stub, the same disposable SQLite DB, and a *new* in-memory FSM store:

| Case | Observed current result |
| --- | --- |
| A. Legitimate coaching user after restart | Normal path yields AI_CHAT and persisted user+assistant exchange. Fresh FSM has no state/data; first returning private text calls the real chat handler but is silently ignored: no generator call, acknowledgement, new DB row, or user reply. Existing conversation ID and two history rows remain. |
| B. New user after fresh memory | Text is ignored and creates neither active session nor chat row. This correctly avoids an accidental new-user coaching entry today. |
| C. DB history but no onboarding proof | An isolated legacy-like users row plus scoped user/assistant history exists. Fresh FSM still rejects coaching. SQLite schema has no onboarding_complete/coaching_eligible column; these row shapes cannot prove how coaching was entered. |
| D. After /new | Normal path then real cmd_new changes current DB ID, stores cutoff, deletes old history, and sets in-process AI_CHAT. Fresh FSM again ignores text. DB retains new ID/cutoff and does not revive old ID/rows. |
| E. Completed quiz before restart | Normal three-answer flow produces FSM archetype “Тень”; normal DB has zero users rows and get_user_profile returns None. Fresh FSM has no archetype. |
| F. Voice after restart | Real voice handler, with Telegram file/download and transcription doubles, performs both file operations and transcription **before** delegating to chat's missing-state gate. Transcript replaces message.text, but no new DB row, model call, or user reply follows. |

The test is intentionally a **current failure proof**. It does not encode future success as skipped/xfail tests or alter handlers to pass. The fake storage accurately models the fact that a new MemoryStorage instance has no previous state, while the SQLite file is kept. A later implementation test should also use real aiogram FSM integration in an environment where aiogram is installed; this offline host does not have it.

## 3. Minimum durable resume contract

Two independent facts must be represented:

1. **Coaching resume eligibility:** a durable, explicit marker written only after a legitimate coaching-entry transition, never inferred from a session ID, chat text, draft, or quiz label. It is per user, survives process restart and /new, and cannot be set by merely receiving a message. The eligibility read must be private-chat gated and read the current DB conversation *without creating a new one merely for the check*. If a marked user entered coaching but never sent a first turn, no active row may exist yet; normal atomic admission may then create the first ID. Where a row exists, admission must preserve its current ID and cutoff.
2. **Quiz context:** an optional, verified quiz result. Only a value written by the actual completed quiz path with known provenance may enrich coaching. Missing, NULL, empty, invalid, or ambiguous legacy result means **no archetype context**; never synthesize “Полутень”. A quiz result alone does not prove that the user clicked into coaching.

This means a small persistent eligibility field is needed. The simplest future location is the existing users table, keyed by user_id, with an explicit coaching-entry marker such as coaching_started_at (nullable). The existing test_result column can store a verified result, provided the quiz path creates/upserts the user row and writes it only after completed scoring. A separate new quiz-completion column is optional only if product rules require auditing completion independently of result; it is not necessary to prove ordinary text resume if the coaching marker is issued at a guarded entry. The current ungated open_ai_chat callback must **not** be treated as sufficient evidence for setting a new durable marker; the later implementation must gate marker issuance on a completed normal quiz transition or another explicitly authorized onboarding path. This is narrowly about who can receive a resume marker, not a stale-callback redesign.

A legitimate already-marked user with no stored quiz result still resumes with archetype=None. Do not make recovery depend on a quiz result whose provenance is missing. A brand-new user, onboarding-in-progress user, user row alone, active-session row alone, and ambiguous legacy history do not qualify.

Proposed same-message text sequence for a later implementation: verify private marker; if FSM is AI_CHAT, use existing path; if FSM is absent, perform a read-only eligibility lookup and read the current active ID if one exists; on confirmed marker, restore the minimal FSM/cache state or route through an equivalent handler-local authorized state, then admit **that exact original message once** through the current atomic DB function. That admission captures the actual active ID and cutoff; do not pre-create an ID for the eligibility check or copy old history. No model call is needed to decide eligibility. If evidence is absent, do not silently promote the user; an explicit restart/onboarding guidance message is a UX design detail for implementation. The first message must not require resending.

For voice, the same private/read-only eligibility preflight should run **before** Telegram get_file/download/transcription when FSM is absent. A valid returning voice message can then use the original marker and the same admission path. This is a follow-on to the first text slice, not a reason to broaden its first implementation.

## 4. Options A–E

| Option | Correctness and onboarding bypass | Legacy handling | Migration/schema impact and complexity | /new and moderation |
| --- | --- | --- | --- | --- |
| **A. Active-session row is enough** | Unsafe: admission can create it on first message; /new can create it for someone who never finished quiz. It proves identity only. | Would incorrectly grant ambiguous rows. | No schema, small handler edit, but wrong contract. | ID is usable, but would turn /new into an unintended resume grant; moderated drafts do not repair proof. |
| **B. Persisted history is enough** | Unsafe: rows record conversation events, not legitimate onboarding. Legacy/imported/direct-entry history is indistinguishable from normal completion. | False positives likely; no reliable backfill. | No schema, small edit, but semantic error. | /new deletes history, so an eligible user's new empty session would lose resume; moderation may lack assistant rows until approval. |
| **C. Explicit persisted coaching/onboarding-complete marker** | Correct if issued only at a validated normal coaching entry; result stays independent. No auto-promotion from rows. | Unknown rows remain unmarked and require /start or verified manual classification. | **Small additive users-table field** plus guarded write/read; existing test_result can be used for new verified results. Medium implementation. | User-level marker survives /new while DB active ID/cutoff remain authoritative; direct and moderated candidates use the same admission decision. |
| **D. Persist quiz result and derive eligibility** | Incomplete: finishing quiz and entering coaching are separate actions, and current /new/open_ai_chat paths can enter chat without quiz. A result may have unknown legacy provenance. | Old result values cannot safely be promoted. | Existing test_result field may avoid schema, but guarded quiz write and unclear semantics remain. | /new could preserve result, but result alone does not prove chat entry; moderation has no effect on that gap. |
| **E. Explicit product state for onboarding and coaching** | Strongest if transitions are specified; can model /start in progress and multiple entry paths. | Can represent unknown state conservatively. | Multiple fields/state machine/migration; largest architecture and regression surface. | Needs additional transition rules for /new and moderated flow; unnecessary for first returning-text recovery. |

**Recommendation: C. SMALL DB PERSISTENCE CHANGE REQUIRED.** A single explicit user-level coaching-entry marker is the minimum authoritative eligibility fact missing today. Pair it with optional verified use of existing users.test_result for context, not for eligibility. The future write must be tied to a legitimate transition, not to the current ungated callback by itself. No automatic legacy backfill from users rows, history, drafts, or active sessions.

## 5. Legacy and /start policy

Legacy database rows may include users.test_result, chat history, active sessions, and drafts without evidence of how they were created. The current schema cannot distinguish a normal completed quiz→coaching route from direct /new or stale open_ai_chat entry, nor establish whether old test_result text came from current scoring. False negatives are preferable: do not set the new marker by heuristic. An unmarked legacy user must re-enter a verified path (or be manually classified from independent evidence, outside this slice). This is a documented one-time inconvenience; there is no safe automatic migration from current rows.

For an existing legitimately marked coaching user who explicitly sends /start, **PRODUCT DECISION REQUIRED** among restart onboarding, resume choice, automatic resume, or keeping current behavior. Current code clears FSM and presents onboarding but leaves DB history/identity intact. No inspected product requirement settles whether /start revokes/suspends resume eligibility. Ordinary text recovery when FSM was lost **without a new /start** can be implemented and tested independently; do not silently turn an in-progress quiz into coaching. If later product semantics make /start a durable restart, that transition needs its own marker/rule. This decision is not made here.

## 6. /new and conversation-ID compatibility

Current /new rotates active_chat_sessions ID, records the cutoff, deletes all user chat rows and PENDING drafts, then sets AI_CHAT in FSM. It does not delete the users row. A future per-user eligibility marker therefore survives a normal /new while the existing active-session ID remains the only history authority. Resume must read the *current* ID when present, not use get_or_create_conversation_id as a probe, not copy old rows, and let admit_user_message apply its existing cutoff. The characterization test proves the current durable new ID and old-history deletion survive fresh memory. Existing session/admission tests cover old-ID conditional-write rejection. The known update-overtaking race is unchanged and not redesigned here.

## 7. Future-behavior test matrix (design only; not executable expectations today)

Each case should use isolated SQLite, private/update doubles (and real aiogram integration where available), zero live model/Telegram calls. The future suite should assert both user-visible routing and exact DB row/ID counts.

| # | Required future assertion |
| ---: | --- |
| 1 | Marked valid returning text user resumes after fresh FSM. |
| 2 | The *first* returning message is processed, without “send again”. |
| 3 | Marked returning voice user passes eligibility before file download/transcription and then reaches coaching. |
| 4 | New user with no marker does not bypass onboarding. |
| 5 | Quiz/onboarding in progress without marker does not bypass quiz. |
| 6 | users row alone is insufficient. |
| 7 | Existing active session is read and restored without creating a second ID. |
| 8 | /new active conversation ID/cutoff are preserved after restart. |
| 9 | Deleted old conversation/history is not resurrected or merged. |
| 10 | Verified persisted quiz result is restored as optional context. |
| 11 | Missing quiz result yields archetype=None. |
| 12 | NULL/empty/invalid result never becomes “Полутень”. |
| 13 | Moderation after resume creates one draft under current ID; approval behavior unchanged. |
| 14 | Group/wrong-chat update cannot resume coaching or start transcription. |
| 15 | Fresh MemoryStorage with the same isolated DB reproduces restart semantics. |
| 16 | Eligibility lookup/recovery makes zero model calls. |
| 17 | One returning user turn is persisted exactly once. |
| 18 | One delivered/approved assistant turn appears exactly once. |
| 19 | Existing current conversation_id remains unchanged on resume; a marked user with no prior active row may acquire a first ID only through normal admission. |
| 20 | Ambiguous unrelated legacy row remains unmarked and is handled conservatively. |

Additional gate for marker issuance: completed quiz→legitimate coaching entry writes exactly one durable marker; a mere /start, users row, quiz-in-progress state, stale ungated entry, or first admitted message must not write it. Test /start behavior only after its product decision is made. Do not solve stale quiz callback integrity in this slice.

## 8. Smallest later implementation slice

First, add the smallest additive nullable coaching-entry marker to users and a read-only eligibility/current-session query. Write the marker only at a verified normal coaching entry. Add a private, absent-FSM-only recovery branch to text handling that processes the same update once through existing admission/generation and preserves the current ID/cutoff. Use no archetype when no verified result is available. Keep quiz result persistence and voice preflight as follow-on increments if needed to keep the first text slice reviewable; neither justifies inventing context. Do not change prompt, conversation-state ledger, moderation, /new race architecture, or onboarding UI as part of this design task.

Validation for this task: targeted characterization tests pass; the full existing test suite and git diff --check are run separately. No runtime behavior was changed.
