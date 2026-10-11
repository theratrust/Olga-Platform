# DEV conversation/session boundary architecture analysis

Scope: source review of feature/method-core at commit 35f0d461ba48758b9be9de176a8e444ec71bc239. This is a proposal, not a description of implemented protection. No running bot, database contents, environment values, or Telegram traffic were inspected.

## Sources and method status

Runtime evidence: [database.py](../../database.py), [handlers/chat.py](../../handlers/chat.py), [handlers/admin.py](../../handlers/admin.py), [handlers/start.py](../../handlers/start.py), [handlers/callbacks.py](../../handlers/callbacks.py), [handlers/voice.py](../../handlers/voice.py), [bot.py](../../bot.py), [coaching_generator.py](../../services/coaching_generator.py), [conversation_state.py](../../services/conversation_state.py), [CONVERSATION_STATE.md](../../services/CONVERSATION_STATE.md), and the synthetic [conversation_benchmark.py](../../services/conversation_benchmark.py). The previous [conversation-state analysis](conversation_state_architecture_analysis.md) describes the ledger's intended scope; some of its line references predate the ledger commit, so current runtime claims below use current source.

The method boundaries are client authorship, no assigned hidden emotions or motives, no diagnosis, no interpretation as fact, and freedom to reject a hypothesis ([границы.md](../method/границы.md), lines 3–39). The behavior specification says to distinguish user words from assistant hypotheses and give later explicit corrections priority ([поведение_AI_бота.md](../method/поведение_AI_бота.md), lines 62–81, 224–244, 325–341). A DB conversation ID, conditional writes, deletion policy, and observer correlation are **derived engineering decisions**, not rules of Olga's method. They must not create new psychological state or model calls.

## Current boundary and identifiers

Today the logical boundary is procedural: /new deletes all chat_messages for a Telegram user, sets FSM state AI_CHAT, and rotates an FSM-only shadow_conversation_id, in that order (handlers/chat.py:35–49; database.py:199–208). There is no stored conversation boundary. /start clears FSM but leaves DB chat rows (handlers/start.py:13–22); open_ai_chat sets AI_CHAT without clearing rows or creating a durable conversation (handlers/callbacks.py:67–80). No session expiry is visible in these paths.

| Identifier | Current scope and limitation |
| --- | --- |
| Telegram from_user.id / chat_messages.user_id | Separates users in SQL; does not separate one user's conversations (handlers/chat.py:40,55; database.py:168–173,189–194). |
| FSM AI_CHAT | Admission state only; MemoryStorage loses it on process restart (bot.py:55–61; handlers/chat.py:57–59). |
| FSM shadow_conversation_id | Random UUID on /new, or fallback during chat; read after user-message save. Passed only to shadow observers, not history SQL, drafts, or generator context (handlers/chat.py:42–44,72–86,214–220). |
| chat_messages.id | SQLite AUTOINCREMENT ordering key, not a session ID. timestamp has default CURRENT_TIMESTAMP but is not used to partition history (database.py:35–45,164–196). |
| pending_drafts.id / created_at | Draft lookup and creation time; drafts contain no conversation ID (database.py:47–56,215–251). |
| Telegram message IDs | Quiz stores last_question_message_id for a different flow; no coaching-history or generation gating (handlers/quiz.py:66,97). |
| Request/generation ID | None found in the coaching write path. The local conversation_id variable is the FSM shadow UUID, not a durable request guard (handlers/chat.py:80–86,123–139). |

The current chat_messages columns are id, user_id, full_name, username, role, content, timestamp (database.py:35–45). get_recent_history selects the last 20 by user_id and descending id, then reverses to chronological order (database.py:164–183; handlers/chat.py:93). The ledger separately reads **all** rows for user_id, ordered ascending, and chooses older eligible evidence outside that same 20-message tail (database.py:186–196; handlers/chat.py:95–111; services/conversation_state.py:108–156). The runtime-memory block is appended to the system message only when nonempty; generate_candidate makes the existing single model call (services/coaching_generator.py:13–34). No separate state is persisted.

The bot routes regular transcribed voice through ai_chat_handler, so the same history and race apply (handlers/voice.py:81–82). Admin voice has a separate prompt and is outside this coaching history path (handlers/voice.py:42–79).

## Exact late-write failure

1. A user turn in conversation A is inserted by user_id, before the handler reads the FSM shadow ID and history (handlers/chat.py:70–99).
2. Generation awaits the provider (handlers/chat.py:123). Concurrent /new can run meanwhile: it deletes that user's chat rows, then sets AI_CHAT and a new shadow UUID (handlers/chat.py:42–44). These actions are separate awaits, not one transaction with the in-flight handler.
3. A conversation B user turn can be stored after deletion. The old A generation may then finish. In direct mode the handler sends A's answer and only then inserts it as an assistant row using user_id alone (handlers/chat.py:130–139). Depending on scheduling, the A row can appear before or after B's first row. Even a /new between send and insert is enough.
4. Subsequent B get_recent_history can include that A assistant row in its latest 20. The unbounded ledger reader can also see it. The extractor rejects one assistant-first pattern (services/conversation_state.py:120–130), but a B user row before the late A assistant row defeats that structural clue. A later B rejection may be incorrectly paired with A's hypothesis, and a contaminated event may be carried forward after it leaves the raw window. This is possible from code order, not evidence of an observed incident.
5. In moderated mode generation can create an A pending draft after /new (handlers/chat.py:146–152). A draft already created before /new also survives because /new deletes only chat_messages. Approval or edit later sends and inserts A's answer by user_id without session validation (handlers/admin.py:100–160,200–255). Rejection of a draft does not write a chat assistant turn.
6. The in-flight handler passes its captured shadow UUID and pre-generation history snapshot to both observers after delivery (handlers/chat.py:210–220). Usually that labels the old generation as A even if its stored answer appears in B; the hash therefore does not certify DB isolation. If /new interleaves before the handler reads FSM data, an old user turn can instead pick up B's shadow UUID. Observer runtimes hash the supplied session_id and use a bounded history snapshot (services/evaluation/runtime.py:117–147,187–220; services/quality_evaluation/runtime.py:78–102,143–175). They do not write chat history. A future /new deletes all accumulated rows again, so it may clear contamination, but it cannot undo an answer already shown or an earlier contaminated generation.

There is another admission race: /new can run between AI_CHAT state check and user-row insertion, or between insertion and the later history read. A generation already admitted as A must retain an A identity through every await. Telegram update ordering alone is not a DB invariant.

## Options

| Option | Benefit | Limit or failure |
| --- | --- | --- |
| 1. conversation_id on chat_messages | Explicit source for user+conversation reads; makes ledger scope inspectable, preserves identity even if rows are retained. Additive nullable migration and one (user_id, conversation_id, id) index are feasible. | A column alone does not stop a stale A insert or admin delivery. Every writer/reader must pass the captured ID, and a durable active-ID check is still needed. Legacy NULL rows cannot be silently assigned to a session. |
| 2. Reuse FSM/shadow ID without schema change | Little schema work; /new already rotates a UUID. | MemoryStorage loses it on restart; it is obtained after the user write; it is absent from chat rows and pending drafts. A SQL user_id read cannot distinguish A from B. It cannot be the authoritative write gate. |
| 3. Persisted generation epoch/token checked before write, without message IDs | An atomic DB-backed token check plus transactional /new deletion can reject late writes in the modeled race. Smaller chat-row schema change. | FSM-only token fails on restart. A separate DB active-token record is still required. Without row identity, readers cannot independently exclude legacy, missed-writer, or previously contaminated rows; drafts still need an epoch. A non-atomic pre-write check has a time-of-check/time-of-use race. |
| 4. Hybrid: durable active ID, ID on chat rows and drafts, conditional writes | DB identity survives restart; every query is scoped; stale direct and moderated writes can fail closed; observer correlation can use the same captured ID. | Small additive migration and updates to all coaching persistence/delivery paths. User-visible send ordering remains a separate race unless /new and delivery are serialized. |

**Recommendation: option 4, limited to conversation identity and stale-work rejection.** It is the smallest design here that makes both read isolation and write rejection verifiable, including moderated drafts. It does not add a conversation summary, LLM call, or psychological interpretation.

## Proposed identity and schema

Use the DB as the source of truth: a minimal active_chat_sessions row (user_id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL) for each chat user. A dedicated row avoids assuming users registration: register_user is defined in database.py:76–86, but no call to it appears in the inspected bot/handler wiring. FSM may cache the ID for UI flow, but a cache mismatch must defer to DB. Generate a random opaque ID on first admitted chat if none exists and rotate it on /new. No separate conversation table, title, summary, or event state is needed.

Add conversation_id TEXT nullable to chat_messages and pending_drafts for an additive SQLite migration. New application writes must supply nonempty IDs. NULL means legacy/unattributed, never “current.” Do not backfill all old rows to one new ID: that would invent a boundary and could bless existing contamination. Decide before migration whether DEV legacy rows should be backed up then cleared or merely excluded from generation; initialize fresh active IDs and fail closed on NULL. A later NOT NULL rebuild is optional after legacy rows are gone, not part of the first slice.

Add one index on chat_messages(user_id, conversation_id, id). Equality on the first two fields supports both latest-20 descending and ledger ascending id scans; its user_id prefix also supports /new deletion. pending_drafts primary-key lookup needs no new index for the current admin path. Keep chat_messages.id as source reference and timestamp as metadata, not as boundary. No model-facing ID is needed.

Both active-ID rotation and chat deletion on /new should occur in one DB write transaction, serialized against conditional inserts. In SQLite, an explicit write transaction such as BEGIN IMMEDIATE makes order clear: an A insert committed before rotation is deleted; an A insert attempted after rotation fails. The active row is keyed by Telegram user ID, so users remain isolated. A second rapid /new rotates again; any generation captured under either prior ID becomes stale.

## Proposed read, write, and lifecycle contract

- **Admission and user save:** Obtain the current DB conversation ID before asynchronous coaching work, creating one atomically if absent. Capture that ID on the request. Insert the user turn with user_id and captured conversation_id only while that pair is still active; if /new won the race, do not reclassify the old turn as B. Return the inserted message ID or a stale result. This also applies to transcribed voice.
- **Generation:** Pass the captured ID through handler control flow, not into the model prompt. Continue using the latest 20 raw messages **within user_id + conversation_id**, in id chronology. Read the older ledger source with the same pair; ideally obtain both from a consistent snapshot so its tail check does not mix concurrent reads. The current message remains authoritative. Do not add a model call.
- **Direct assistant save:** After generation, check active ID before user-facing send; discard if stale. Persist only with an atomic conditional insert that verifies captured ID equals the DB active ID in the same write transaction. Checking once and then doing an unconditional insert is insufficient. Avoid treating a rejected insert as delivered history.
- **Moderated draft:** Conditionally create a draft bearing captured ID only while active. On approve or edit, compare draft user_id + conversation_id to DB active ID before send, and conditionally insert the delivered assistant row against that ID; stale or NULL-ID drafts must be rejected/retired. A pending draft is not a chat assistant turn until actually delivered. Consider invalidating that user's pending drafts in the /new transaction; existing admin notifications then resolve as stale.
- **Observers:** Supply the captured DB conversation ID, rather than an independently rotating FSM UUID, as session_id to both shadow observers. They may continue logging only a hash. A stale generation should not be logged as a B delivery; whether to record a separate non-content stale-discard diagnostic is a later observability choice. Observer outputs never determine the active session.
- **/new:** Rotate the DB active ID and delete that user's old chat rows atomically. Clear/synchronize the FSM shadow cache and set AI_CHAT after the DB transaction; the DB identity remains authoritative even if the FSM update fails. Invalidate old drafts. /start remains a UI/FSM reset unless product semantics explicitly change; reentering AI_CHAT resumes the DB active conversation rather than creating a hidden new one.
- **Restart/FSM loss:** DB ID and tagged messages survive. The current MemoryStorage still loses AI_CHAT and archetype, so the user may need to reenter chat as today; reentry must reuse the DB active ID. Missing FSM data must never rotate the DB ID implicitly. If no DB active row exists, create a fresh ID; exclude NULL legacy rows.
- **Concurrent work:** Capture one ID per admitted turn. Atomic DB write conditions, not a read-then-write in Python, reject stale records. Two ordinary messages under the same current ID may both be admitted, but their model replies can still complete out of order; that is a separate ordering problem, not cross-session leakage.

The exact read predicate is chat_messages.user_id = ? AND chat_messages.conversation_id = ?. The same predicate applies to latest-20 and full ledger reads. Draft ownership additionally requires pending_drafts.user_id and its conversation_id to match the active row. Never query older ledger evidence by user_id alone.

A DB gate guarantees stale content is not *stored* in B. It cannot alone make a Telegram send and a DB rotation atomic: /new could occur between a pre-send check and the network send, including in admin approval. For a strict user-visible no-late-answer guarantee in the current single polling process, serialize /new and final check/send/write per user, while still retaining the DB conditional write as the durable guard. A process-local lock does not cover multiple bot processes; deployment with more than one writer would need a shared per-user queue/lease or equivalent ordered delivery. Do not hold a SQLite write transaction across the network call. This delivery concern is a production gate, not a reason to let old rows into history.

## Retention, privacy, and compatibility

Recommend **preserving current /new chat-row deletion**, not retaining old conversations under IDs. It matches the present “previous history cleared” user message (handlers/chat.py:46–49), minimizes retained sensitive coaching text, and keeps the first slice small. The ID remains useful as a fence and for exact reads even though old rows are deleted. Old pending drafts contain user text and model text in a separate table; they must be invalidated and handled under an explicit retention policy rather than silently approved later. Admin Telegram notifications already sent cannot be recalled by a DB migration. Retaining A rows for debugging or analytics would change privacy expectations and needs a separate product decision.

Migration concept for DEV: back up the DEV SQLite file under the approved operational procedure; add nullable ID columns and the active-ID table/index; deploy code that writes IDs and scopes all reads; initialize active rows on first chat or /new; reject legacy NULL draft approval; verify no user_id-only chat history path remains. Additive migration permits old binaries to start, but old writers would insert NULL and violate the safety invariant, so version compatibility is **operationally unsafe**: deploy migration and new single-writer runtime together, and do not run old and new workers concurrently. PROD's schema stays untouched pending separate approval.

Rollback: disable the ledger carry-forward and stop/restore the new runtime from the DEV backup if necessary; leave additive columns/table in place for a reversible code rollback, rather than immediately dropping data. Reverting to old code also reopens the baseline late-write race, so it is not a safe production fallback with the ledger enabled. A complete rollback requires quiescing in-flight work and returning to the prior documented DEV behavior. Never map NULL legacy rows into an active conversation merely to preserve continuity.

## Offline validation before production

1. Race an A generation against /new, then start B: A answer is neither stored nor in B's latest 20/ledger; direct-mode delivery should be rejected if reset precedes final send.
2. Assert the conditional assistant insert loses to rotation after the active ID changes; check both transaction orders (A commit then deletion, rotation then rejected A insert).
3. Exercise moderated A draft creation before and after /new, then approval and edited approval: stale/NULL draft never writes into B or sends as current.
4. Scope user and ledger queries to B even if A-tagged rows are deliberately left in a test fixture; two users with coincident ID strings remain isolated by user_id.
5. Restart with active DB identity and lost FSM: reentry uses the same ID; fresh ID only where no DB active row exists. Test NULL legacy chat rows and drafts fail closed.
6. Run concurrent same-session messages, /new during generation, and two rapid /new calls; verify each captured ID and latest-20 chronological ordering.
7. Verify observer session hashes follow captured A/B IDs and never turn a stale A generation into a B delivery record. Test transcribed voice through the shared chat handler.
8. Keep the synthetic benchmark unchanged initially: it uses an in-memory per-scenario UUID and history[-20:], with no Telegram/FSM/DB (services/conversation_benchmark.py:177–209). Add offline DB/handler race tests; adapt the benchmark only if a later experiment explicitly tests session transitions. No new evaluator dimension is required.

## ADR

**Decision.** Add a DB-authoritative active conversation ID, tag chat rows and pending drafts, scope reads by user_id + conversation_id, rotate/delete atomically on /new, and reject stale writes with a DB-conditional insert. Align observer correlation to the captured ID. Keep the existing 20-message raw window and deterministic ledger semantics within that scope.

**Why.** A durable ID plus atomic write fence closes the known late-write storage race, makes ledger isolation independently testable, and survives restart without adding model or psychological state.

**Alternatives rejected.** Chat-row ID alone does not fence late writes; FSM/shadow ID is volatile and not on rows; a token-only gate without row IDs cannot prove read provenance or quarantine legacy contamination; retaining all past conversations changes privacy and scope.

**Risks.** Missing one write path (especially admin approval), user-visible send/rotation race, legacy NULL rows or old workers, non-atomic migration, and concurrent reply ordering. The first four are release gates; the fifth is a separate conversational ordering concern.

**Migration strategy.** Add nullable columns, active-ID table, and composite index in DEV; deploy all readers/writers together; initialize new IDs without guessing legacy boundaries; test a copy of DEV data before any live rollout. No PROD migration is part of this decision.

**Rollback strategy.** Quiesce in-flight work, disable ledger carry-forward, restore prior DEV runtime or backup as needed; retain additive schema until a separately reviewed cleanup. Do not claim old code preserves the new boundary guarantee.

**First implementation slice.** Implement only active-ID creation/rotation, tagged chat and draft writes, scoped latest-20/ledger reads, atomic stale-write rejection for direct and admin paths, and offline race/restart/legacy tests. Preserve current /new deletion, prompt, evaluator logic, and model-call count. Verify user-visible delivery serialization separately before calling the slice production-ready.
