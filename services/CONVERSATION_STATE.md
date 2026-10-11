# DEV conversation-state carry-forward

This experiment carries only explicit older user boundaries/corrections and explicit rejection of an assistant hypothesis. It does not infer motives or goals, track active themes, or use an LLM summarizer.

## Conversation boundary

The SQLite active_chat_sessions row is the source of truth for each Telegram user. New chat_messages and pending_drafts carry its opaque conversation_id. The latest 20 raw messages and the older deterministic ledger source are both read by user_id plus captured conversation_id. The ledger still contains at most four source-linked items and is never stored separately.

On first chat use, a new active ID is created. /new rotates that ID and deletes the user's chat rows and pending drafts still marked PENDING in one DB write transaction. New user/assistant rows and pending drafts use conditional inserts that reject a captured ID after it becomes stale. Approval/edit of a pending draft checks the active session and conditionally persists the delivered assistant turn. The FSM shadow ID is only a cache for observer correlation; it cannot authorize a DB write.

The schema upgrade is additive and repeat-safe: nullable conversation_id columns, nullable cutoff_chat_id/cutoff_message_id columns on active_chat_sessions, and a composite chat-history index. Legacy NULL rows are never assigned to a new session or read into its history. /new deletes them. No running database migration is performed by writing this code; init_db upgrades the configured DB only when that runtime is next started.

## Private-chat admission boundary

End-user coaching is private-chat only. /new, coaching text/voice, /start, quiz callbacks, and the AI-chat entry callback ignore non-private chats without changing coaching FSM, history, or drafts. Admin/moderation control paths retain their existing behavior. Private inbound turns use their original Telegram chat ID and positive message ID; transcribed text never supplies a synthetic marker.

/new records its chat/message cutoff while rotating the DB conversation ID and deleting old rows/drafts in one SQLite write transaction. An atomic user admission transaction checks that a private inbound message is newer than that cutoff, inserts it, and returns the captured conversation ID. Stale, missing, or incomparable markers are rejected without generation or a draft. An older /new cannot replace a newer cutoff. The DB cutoff is the persistence correctness fence; the short per-user asyncio lock only coordinates local FSM and DB admission and is released before generation. The lock is process-local, disappears on restart, and does not establish deterministic processing order across multiple bot workers. Scaling beyond the current single polling process needs stronger ordered ingress coordination before production use.

## Remaining limits

A response can still be **sent** after /new if the reset occurs between the send-time active-ID check and Telegram delivery. The later DB insert is rejected, so persistence and ledger contamination are prevented, but user-visible send ordering still needs a separate pre-production solution. The same gap applies to moderated approval/edit. A valid post-/new message can still be processed before the reset handler and be deleted with the old conversation; the cutoff prevents an older message from entering the new conversation, but cannot recover this overtaken newer turn. Replies to concurrent messages inside one active conversation can finish out of order.

The older-history ledger query remains unbounded **within the current conversation**. The existing deterministic event detector may omit ambiguous statements by design. No extra model call, prompt change, or evaluator dimension is introduced. This remains DEV-only, not production-ready.
