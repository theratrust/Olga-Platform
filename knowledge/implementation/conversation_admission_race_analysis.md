# Admission boundary for Telegram coaching messages (DEV architecture analysis)

Status: analysis only. No runtime, schema, prompt, test, evaluator, or benchmark change is made here. This decision is scoped to the current DEV polling bot and the inbound admission race; the send race remains separate.

## Evidence and current behavior

- `bot.py:57,201` constructs `Dispatcher(storage=MemoryStorage())` and calls `start_polling(bot)` with defaults. The installed DEV aiogram is 3.30.0; its polling default is `handle_as_tasks=True`, and this dispatcher's event isolation is `DisabledEventIsolation` (read-only runtime inspection). The code registers no admission middleware or queue. Thus the order in which two handler tasks reach an await or an application lock is **not guaranteed** to match Telegram message order. [aiogram dispatcher 3.30](https://docs.aiogram.dev/en/v3.30.0/dispatcher/dispatcher.html).
- The checked DEV Compose file defines one bot service, and the observed DEV deployment had one `python bot.py` bot container. The coaching database in `database.py` is SQLite via `aiosqlite` and `DB_PATH`; the Compose Postgres service is not used by this module. No assertion about PROD process topology is made because PROD was not inspected. A second bot process or poller is possible in another deployment and would not share Python locks.
- `handlers/chat.py:38-49` handles `/new`: `rotate_conversation(user_id)` commits a new DB ID and deletion, then separate FSM awaits set `AI_CHAT` and the observer's shadow ID, then it answers. `database.py:193-208` uses one `BEGIN IMMEDIATE` transaction for rotation, chat-row deletion, and pending-draft deletion.
- `handlers/chat.py:52-82` checks `state.get_state()` before calling `get_or_create_conversation_id(user_id)`, then awaits `send_chat_action`, then conditionally inserts the user row. The **current admission point** is that successful user-row insert, not receipt of the Telegram update, handler invocation, or FSM check. The captured DB ID is obtained at line 72. `database.py:211-229` atomically verifies that *the supplied ID is active*, but it cannot know whether the inbound update predates the latest `/new` when that ID was fetched after the reset.
- `handlers/voice.py:20-34,81-82` downloads and transcribes a non-admin voice/audio message before delegating to the same chat handler; it preserves the original `Message` object and so has a larger pre-admission interval. `handlers/start.py` and quiz/callback flows can change FSM state; FSM state is a UI gate, not conversation identity. `handlers/admin.py` performs later approval/edit of pending drafts, using the already captured draft ID/session checks.
- History uses `get_recent_history(user_id, conversation_id, limit=20)` in `handlers/chat.py:98`; ledger source uses `get_conversation_history_with_ids(user_id, conversation_id)` at line 103. Both SQL predicates use `user_id + conversation_id` (`database.py:232-251`). The runtime ledger is derived from those rows, not stored separately. `create_pending_draft` is also conditional on the captured ID (`database.py:254-271`).
- Existing offline tests cover stale **assistant** writes, stale drafts, `/new` deletion, rapid reset, restart, and scoped history (`tests/test_conversation_sessions.py`, `tests/test_conversation_state.py`). They do not establish a Telegram-order admission fence for a handler that fetches its ID after `/new`.

## Exact race and interleavings

For an ordinary text update U sent before reset update N:

1. Aiogram receives U and schedules its task. U may not start immediately, or it may enter `ai_chat_handler` and suspend at `state.get_state()`; a voice U may still be downloading/transcribing.
2. N's task runs `rotate_conversation`, changing active A to B and deleting A rows/drafts. It then updates FSM.
3. U resumes and calls `get_or_create_conversation_id`; it receives B. Its user insert passes the atomic active-ID predicate because B **is** active. The row is now a B row despite U preceding N.
4. B's latest-20 history contains U. If U has an eligible explicit boundary/correction, the ledger may later carry it after it leaves the latest 20. A direct response or moderated draft generated from U may also be tagged B. Existing stale-assistant/stale-draft guards then see B as valid and cannot repair this misclassification.

If U captures A before N rotates, its insert either commits first and is deleted by N, or is rejected after rotation. That path is safe for persistence. Capturing at the first line of the handler only shortens the interval: N can run after update receipt but before handler entry. An in-process mutex acquired at handler entry also does not prove which task acquires first. N can overtake U before the mutex; U would still fetch B unless the update itself carries an independent ordering fence.

Other orderings matter. A message sent **after** `/new` may be processed before N's handler and temporarily inserted under A, then deleted when N runs. This is message loss, not A-to-B contamination. Two `/new` tasks can also execute out of Telegram order; the older reset must not overwrite the newer one. The admission design should detect both cases; it cannot promise preservation of all post-reset messages without ordering intake before concurrent handler tasks.

## Telegram identifiers and ordering: verified versus assumed

`Update.update_id` is available on aiogram's update context (`event_update`) but is not a `Message` field and is not passed to today's chat or voice handlers. Telegram says update IDs normally increase sequentially and help restore order, **but the next ID can be random after at least a week without updates**. A permanent numeric `update_id > cutoff` predicate is therefore not a safe sole boundary; it can reject valid new updates or misorder a delayed task across an epoch reset. [Telegram Bot API, Update](https://core.telegram.org/bots/api#update), [aiogram context data](https://docs.aiogram.dev/en/v3.30.0/dispatcher/dependency_injection.html).

`Message.message_id` and `Message.chat.id` are already present on incoming text and voice messages, though current coaching admission ignores them. The Bot API documents message-ID uniqueness **within a chat**, including a possible zero ID for an ephemeral/unusable message; it does not by itself state a monotonic ordering rule. Telegram's underlying message-update documentation says ordinary private/basic-group message IDs are monotonically increasing and used to order messages. This supports a **same-chat, ordinary-message** cutoff, not comparison across chats, bot accounts, business connections, or exceptional message types. Treat private-chat scope and positive IDs as explicit preconditions, and verify that mapping with offline fixtures and a separate non-live contract review before implementation. [Bot API, Message](https://core.telegram.org/bots/api#message), [Telegram message sequences](https://core.telegram.org/api/updates).

`Message.date` is second-resolution and does not order messages within a second; neither local receipt time nor handler start time proves Telegram send order. Do not use timestamps as the admission cutoff. The current bot keys session identity by `from_user.id` but does **not** restrict coaching handlers to private chats. Because message IDs cannot be compared across chats, the minimal design below must fail closed for non-private, missing-chat, zero-ID, or otherwise incomparable inbound updates; supporting the same user across several Telegram chats requires a separate, explicit ordering design. This is a scope/compatibility risk, not a property already enforced by the code.

## Options

| Design | Benefit | Remaining failure or cost |
| --- | --- | --- |
| 1. Fetch ID at handler entry | Very small change; closes awaits later in the handler. | Update receipt to handler entry remains a gap. A pre-`/new` U can enter after N and fetch B. Voice preprocessing makes the gap larger. Insufficient alone. |
| 2. Per-user `asyncio.Lock` around admission and `/new` | Serializes DB/FSM admission sections for one process and lets different users proceed; release before model generation. | Lock acquisition order is task scheduling order, not Telegram order. Restart destroys locks; second process has different locks. Insufficient alone. Do not use aiogram's full-handler FSM isolation because it could hold the lock across model generation and applies its own chat/user strategy. |
| 3. Conditional DB insert using current conversation ID | Survives restart and atomically rejects a previously captured stale ID. | Already exists for user rows. If lookup itself occurs after N, U is incorrectly given B and passes. Requires a pre-existing, Telegram-order token or cutoff. |
| 4. Telegram boundary marker | A `/new` message's `(chat_id, message_id)` can distinguish older ordinary messages in the **same private chat**, even when their handlers run late; store it with B and check atomically. | Requires a small DB column addition and positive/private-message gate. A global update-ID cutoff has the week-reset caveat. Message ID alone cannot fence other chats. |
| 5. Hybrid: per-user short mutex + DB-bound same-chat `/new` marker | Mutex coordinates in-process FSM/DB admission; durable DB predicate still protects delayed tasks and multiple processes; no lock during generation. | Does not preserve every post-`/new` update if tasks overtake one another before admission. Must fail closed outside comparable private-chat events. |

## Preferred architecture: short local admission lock plus durable DB cutoff

Use the existing `active_chat_sessions` row as source of truth. Conceptually add nullable `reset_chat_id` and `reset_message_id` for the most recent accepted `/new`; no new conversation table or model call. An initial NULL marker means no `/new` boundary has yet been recorded for that active row. The first guarded `/new` stores its positive private-chat message ID with the newly rotated conversation ID **in the same SQLite transaction** that deletes prior rows and pending drafts. Subsequent `/new` messages must have a larger message ID in that same chat; an older reset is rejected rather than rotating backward. Never infer a new session from FSM data.

For normal coaching text and transcribed voice, pass the original Telegram message metadata unchanged into admission. A single DB transaction should read/initialize the current active row and conditionally insert the user turn only if the inbound marker is comparable and strictly newer than the stored `/new` marker (or the marker is NULL before any reset). The transaction returns the actual conversation ID used; generation and draft creation carry that exact ID. There must be no separate “read active, then check marker, then insert” window. Keep the existing active-ID conditional writes for assistant turns/drafts and the existing `user_id + conversation_id` history/ledger filters. `/new` must compare and update its marker and rotate/delete in one DB write transaction.

For this narrow private-coaching design, require `message.chat.type == private`, `message.chat.id == message.from_user.id`, and a positive ordinary `message_id` on both coaching turns and `/new`. Reject incomparable updates from admission; do not silently assign them to B. This is an explicit proposed compatibility restriction because current code has no such gate. If group/business-chat support is required, defer implementation of this recommendation until a shared global ordering mechanism is designed; never assume a private-chat marker orders another chat. `update_id` can be captured for non-sensitive diagnostics/fixture assertions, but it is not the authoritative cutoff. Do not store or compare timestamps for session authority.

### Critical sections

**Normal message, same-user lock:** (1) validate the inbound source marker and obtain/check the current FSM chat state; (2) in one short DB transaction, get/create the active row, compare its `/new` marker with the inbound marker, and insert the user text tagged with the returned ID; (3) capture that ID for the remaining handler; (4) release the lock. Load latest 20, ledger, generate, notify/send, and create assistant/draft writes outside the lock; their existing conditional ID checks remain. Voice download/transcription may occur before this section, but must carry the original message marker and cannot remap on conflict. A per-user lock should be keyed by the same user identity as the DB row, and lifecycle/cleanup of idle lock objects should be bounded.

**`/new`, same-user lock:** (1) validate the reset marker; (2) one DB transaction compares it against any prior marker, rotates the active ID, stores the cutoff, deletes old chat rows and pending drafts, or rejects an older duplicate; (3) update AI_CHAT and the observer's shadow ID while still holding the lock; (4) release before Telegram acknowledgement. The DB commit and in-memory FSM update cannot be one atomic transaction. If the FSM update fails after DB commit, B remains authoritative; fail closed for subsequent admission until the UI state is reconciled, with no fallback to A. A reset DB failure leaves the previous ID/rows/marker intact and must not advance FSM.

The lock is useful for local admission/FSM coordination but **the DB cutoff is the cross-process safety fence**. No SQLite transaction or Python lock spans OpenRouter generation or a Telegram network send. The unresolved send-after-`/new` race is unchanged. Same-conversation assistant completions may still be out of order.

### Failure and observability

For a stale or incomparable inbound message, do not write user text, generate a coaching answer, make a draft, or retry it under the current ID. Return a deterministic rejected-admission result. A neutral acknowledgement may be considered during implementation to avoid silent user-visible loss, but no copy is specified here. Log/metric names may include `stale_inbound_rejected`, `admission_boundary_conflict`, operation kind, and a one-way session hash. Never log raw user ID, raw conversation ID, raw text, raw Telegram marker values if they would identify a user, or provider payloads. DB errors should roll back and fail closed; distinguish them from an ordinary stale event.

### Multi-process, restart, and moderated mode

Current DEV has one observed bot process; a per-user Python lock works only inside it. It disappears on restart and is not shared by a second worker. The DB transaction and persisted cutoff must remain sufficient to reject a delayed pre-reset insert even when no local lock is shared. Multiple pollers/worker dispatch can still lose valid post-reset messages by processing N and later messages out of arrival order; production-level ordered admission across workers needs a shared queue or stronger ingress protocol. PROD topology is unverified and cannot be inferred from DEV.

Moderated mode shares the same inbound user-message admission, so the new fence must run before history assembly and draft generation. Otherwise a pre-reset U misadmitted into B produces a B-tagged draft that correctly passes today's approval check. Once user admission is correct, `create_pending_draft` and admin approval/edit retain their existing conversation-ID gates. Admin callback order is not a substitute for inbound admission order, and the separate approval send race is not addressed here.

## Offline test strategy for the first implementation slice

1. Pause U before DB admission, process N, resume U: reject U; B history and ledger stay clean.
2. Process N first, then a genuinely later private-chat U with larger message ID: admit into B.
3. Two same-user normal turns: admit with the same active ID; lock covers only the short admission sections.
4. Two users: lock and marker for one user do not block or affect the other.
5. U1, N, U2: U1 cannot enter B; U2 is admitted when processed after N. Also exercise reverse task scheduling and document that a valid U2 processed before N may be deleted from A.
6. Two rapid `/new` updates processed in reverse task order: the higher message ID remains the only active reset; older reset cannot rotate backward.
7. Moderated U before N is rejected after N and cannot create a B draft; a valid B draft still follows ordinary approval rules.
8. Recreate lock manager/FSM as on restart and retain disposable SQLite fixture: the DB marker still rejects stale U.
9. Simulate two independent lock managers sharing one fixture: DB transactions, rather than shared Python locks, enforce no A-to-B persistence; assert the documented availability/ordering limit.
10. Assert private-chat and positive-ID preconditions; group, mismatched chat, zero/missing ID, and raw update-ID week-reset cases fail closed or never use `update_id` as authority.
11. Inject DB failure inside normal admission and `/new` transactions: rollback leaves no partial row, marker, rotation, or deletion; FSM does not advance on failed reset.
12. After more than 20 B turns, confirm latest-20 and ledger read only B rows and no rejected A text appears. Keep prompt, evaluator, and benchmark scenarios unchanged; all tests offline.

## Architecture decision record

**Decision.** For ordinary private coaching messages, add a durable same-chat `/new` message-ID cutoff to the DB active-session row and atomically check it when inserting user turns; coordinate local admission and `/new` FSM work with a short per-user lock. Reject stale or incomparable inbound updates. Preserve existing conversation IDs, scoped reads, conditional assistant/draft writes, deletion semantics, and model behavior.

**Why.** The current active-ID check cannot distinguish an old update that fetched B after reset. The cutoff supplies Telegram send-order evidence independent of handler scheduling; the lock keeps same-process DB/FSM admission sections coherent. A short critical section leaves generation concurrent.

**Alternatives rejected.** Earlier ID capture and a handler-entry lock alone lack a receipt-to-handler ordering guarantee. A DB token looked up after `/new` repeats the bug. A bare `update_id` cutoff can break after a week of inactivity. Full-handler serialization would hold across long generation and affect other users. An ordered multiprocess ingress queue is broader than this DEV slice.

**Critical section.** Normal: FSM gate, atomic marker check + user insert + ID capture. Reset: atomic marker compare + ID rotation + row/draft deletion, then FSM update before releasing the same user's lock. No network/model work inside.

**Failure behavior.** Stale/incomparable inbound is rejected without persistence, draft, generation, or remapping. Transaction failure rolls back; DB remains source of truth if FSM repair is needed. Neutral user acknowledgement is a separate implementation choice.

**Single-process/multi-process implications.** The lock improves current single-process DEV ordering but is not a distributed guarantee. The persisted cutoff and conditional insert protect cross-session history across restart/workers for comparable private-chat messages; preserving all valid message delivery under out-of-order multiprocess intake requires later work.

**Risks.** (1) Current handlers accept non-private chats; failing closed changes that behavior. (2) Bot API documents message-ID uniqueness while the monotonic rule is documented in Telegram's underlying update model, so the ordinary-private-chat precondition needs contract review. (3) Concurrent task order may lose a valid post-reset turn even when it cannot leak an older turn into B. (4) DB/FSM update is not atomic. (5) Send-after-reset and same-session completion ordering remain unresolved production gates.

**Rollback strategy.** Revert the admission code and stop using the nullable cutoff columns in DEV; an additive column can remain unused. Do not run old and new writers concurrently, because old code would ignore the cutoff. This analysis performs no migration or rollback.

**First implementation slice.** In DEV only, add nullable reset-chat/message marker columns to `active_chat_sessions`; add a small per-user admission-lock helper and one atomic DB admission function; make `/new` store/compare its marker in the existing transaction; pass original marker through text and voice handlers; reject stale/incomparable events; add the offline tests above. No prompt, model-call, evaluator, benchmark, send-race, or PROD change.
EOF'