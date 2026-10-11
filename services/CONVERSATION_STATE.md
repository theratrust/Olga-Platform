# DEV conversation-state carry-forward

This experimental runtime context keeps a few explicit user statements available after they leave the latest 20-message history window. It carries only older user boundaries or corrections and explicit rejections of a preceding assistant hypothesis. Each item retains source message IDs and short user wording.

## Scope

The normal latest 20 raw messages remain unchanged and in chronological order. A deterministic reader inspects older chat rows and selects at most four eligible items. The generator receives them as a labeled runtime data block. No separate ledger is persisted, and no additional model call is made.

This is not a psychological summary. It does not infer motives or goals, track active themes, or use an LLM summarizer.

## Safety and limits

False negatives are preferred over false positives: ambiguous events are omitted. The current user message and explicit later corrections take priority over carried-forward state.

The older-history query currently loads all stored rows for the user and is unbounded. Chat rows have no `conversation_id`. A late assistant write after `/new` can cross the logical session boundary and enter the next raw history window. The extractor excludes an assistant-first history from rejected-hypothesis carry-forward, but it cannot resolve every late-write interleaving without a reliable persisted session boundary.

This slice is DEV-only and not production-ready.
