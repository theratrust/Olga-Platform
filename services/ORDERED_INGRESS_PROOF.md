# Ordered ingress with aiogram 3.30 — offline proof

Status: **proof only; not wired**. `bot.py`, handlers, the real DB schema, prompts, and benchmark remain unchanged. The aiogram probe runs a real Dispatcher against fake `Update` objects in the installed DEV container. It patches the update source and bot identity only inside the probe, so it makes no Telegram or model request. Host pytest drives that probe through `docker compose exec`; it needs the existing DEV image because host Python has pytest but no aiogram. SQLite proof storage is in memory or a disposable pytest path, never the configured DEV DB.

## Public seam and result

Installed aiogram is 3.30.0. `Dispatcher.start_polling(handle_as_tasks=False)` awaits `_process_update` for each received update. `Dispatcher.feed_update` invokes the registered update outer middleware on that awaited path. The proof registers a middleware through `dispatcher.update.outer_middleware(...)` and runs the real public `start_polling` method, with a test-only fake update source. No private `_polling` override is used in runtime or proof. The version test fails on a different aiogram version or if the assumed API/ordering behavior changes.

For received private messages 101 text, 102 `/new`, 103 text, the middleware commits admissions in exactly 101, 102, 103 order. Its immutable `Decision` captures A for 101 and B for both 102 and 103. It copies aiogram middleware data to hand that result to a detached handler. A supervised downstream task for 101 waits while 102 and 103 are admitted. The 102 downstream task also waits while 103 starts and finishes. Completion can be 103, 102, 101 without changing captured IDs. These barriers are event based; no sleep duration determines correctness. A single scheduling yield only collects tasks already launched. Successful acknowledgement is modeled inside downstream after committed admission and before generation; rejected/failed ingress launches none.

This proves the **public API composition** for the restricted message path. It does not prove parity for every existing handler, `TelegramMethod` return, callback, quiz, or FSM transition. Returning immediately from middleware means aiogram considers the update handled before detached work finishes. Detached task exceptions must be observed separately.

## Task supervision and failure

`TaskSupervisor` retains task references until completion, retrieves exceptions, removes completed tasks, and supports explicit drain or cancellation. The proof tests downstream error observation and shutdown cancellation. A future runtime must choose a bounded graceful shutdown window, then cancel remaining work, with safe diagnostics. Awaiting all tasks indefinitely would hang shutdown; cancelling immediately can lose generated responses. The proof does not choose production policy or implement backpressure.

An injected SQLite admission exception for 102 propagates through middleware, but aiogram 3.30 `_process_update` catches it, logs it, returns `True`, and continues to 103. Thus this public seam **does not stop polling on DB failure**. In the fake stream, 102 has no commit or acknowledgement and 103 attaches to A because `/new` did not commit. In real polling, aiogram `_listen_updates` advances its local offset when iteration resumes; a later `getUpdates` request with the higher offset can confirm the failed update. Raising an exception alone is not retry/fail-stop. This is an update-loss and session-boundary readiness blocker until explicit ingress failure policy is designed and tested.

## Disposable DB feasibility

`ProofStore` models proposed primitives only; it is not a migration. Its unique key `(user_id, chat_id, message_id)` prevents duplicate text rows and duplicate `/new` rotations. The first `/new` commits a new active ID and cutoff; replay of the same marker returns `duplicate`. Telegram message-ID gaps are not treated as missing work. Other users have separate active rows. Transaction faults roll back all active/admission/history changes.

Voice admission writes only a durable marker, captured conversation ID, and `reserved` status. The transcript later commits once if the same reservation and captured ID are still active. Empty/failed transcription marks it failed without a history row. A `/new` between reservation and transcription rejects the late commit. Reopening the disposable SQLite file retains the reservation. No fake placeholder user text appears in history. A real schema and retention/recovery policy would be needed for wiring; this proof does not modify `database.py`.

## Restart and delivery boundaries

| Crash point | Durable state in proposed model | Delivery/recovery limit |
| --- | --- | --- |
| Update received before admission commit | No new admission/history/reset. | Replay depends on Telegram offset confirmation and pending-update policy; do not assume redelivery. |
| Admission committed before downstream launch | Text row, `/new` cutoff, or voice reservation remains; no answer launched. | Duplicate replay is fenced, but it does not itself resume generation. User-visible answer may be lost. |
| Downstream launched then process dies | Admission remains; incomplete task disappears. | User may have no answer, partial acknowledgement, or uncertain delivery. |
| Voice reserved before transcription commit | Reservation remains, no history row. | Restart can detect it, but recovery/retranscription is not implemented. |

In installed aiogram `_listen_updates`, `getUpdates.offset` is assigned after yielding an update; Telegram confirmation occurs when a later request carries that higher offset. The proof does not call Telegram and does not simulate server confirmation. Current `bot.py` calls `delete_webhook(drop_pending_updates=True)` before polling. On restart this can discard queued updates, including work left unconfirmed. That choice is incompatible with a promise to recover every coaching turn after a crash; it needs a separate product/operations decision before wiring. Even changing it would not recover already confirmed but unprocessed downstream work.

## Scope and operational invariant

Only private text, private voice markers, and `/new` are modeled. Callback queries have no comparable incoming Message marker; quiz and `/start` FSM transitions need separate coordination with `/new`. Admin/moderation paths are not exercised. The real voice handler currently transcribes before admission; later wiring would move reservation before transcription and pass the immutable result downstream without a second admission. The real text and `/new` handlers would likewise consume the captured result and not repeat DB work.

The guarantee assumes **exactly one polling owner for the bot token**, and one Bot passed to `start_polling`. Current Compose shows one DEV bot service, but repository inspection cannot rule out an external process using the same token. A later deployment should enforce a local single-owner startup lease/lock and monitor duplicate-poller errors; a process-local lock does not coordinate multiple workers. No such guard is implemented here.

**Readiness: NOT READY FOR DEV WIRING.** The ordered public aiogram seam, supervised downstream tasks, text and `/new` dedupe, and voice reservation are feasible. The DB-failure path can lose `/new` and let a later turn attach to the wrong session. Before wiring, define and offline-test a fail-stop/retry or durable inbox policy, restart/pending-update policy, task shutdown/backpressure, and the deferred FSM/handler handoff. Send-after-/new and same-session completion ordering remain separate risks.
MD'