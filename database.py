import os
import aiosqlite
from uuid import uuid4

DB_PATH = os.getenv("DB_NAME", "bot_data.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                subscription_status TEXT DEFAULT 'PENDING',
                test_result TEXT,
                answers TEXT,
                coaching_eligible INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT,
                category TEXT,
                title TEXT,
                content TEXT,
                status TEXT DEFAULT 'PENDING',
                approved_by TEXT,
                approved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                username TEXT,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                user_message TEXT,
                ai_draft TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                message_id INTEGER,
                text TEXT,
                updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Additive, repeat-safe DEV upgrade. Legacy users remain ineligible.
        async with db.execute("PRAGMA table_info(users)") as cursor:
            user_columns = {row[1] for row in await cursor.fetchall()}
        if "coaching_eligible" not in user_columns:
            await db.execute(
                "ALTER TABLE users ADD COLUMN coaching_eligible INTEGER NOT NULL DEFAULT 0"
            )

        # NULL legacy conversation rows remain unattributed.
        for table in ("chat_messages", "pending_drafts"):
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if "conversation_id" not in columns:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN conversation_id TEXT")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_chat_sessions (
                user_id INTEGER PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                cutoff_chat_id INTEGER,
                cutoff_message_id INTEGER
            )
        """)
        async with db.execute("PRAGMA table_info(active_chat_sessions)") as cursor:
            session_columns = {row[1] for row in await cursor.fetchall()}
        for column in ("cutoff_chat_id", "cutoff_message_id"):
            if column not in session_columns:
                await db.execute(f"ALTER TABLE active_chat_sessions ADD COLUMN {column} INTEGER")
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
            ON chat_messages(user_id, conversation_id, id)
        """)
        await db.commit()


# --------------------------------------------------------------------
# Users
# --------------------------------------------------------------------

async def register_user(user_id: int, full_name: str, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, full_name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                full_name = excluded.full_name,
                username = excluded.username
        """, (user_id, full_name, username))
        await db.commit()


async def update_user_test_result(user_id: int, answers: str, test_result: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users
            SET answers = ?, test_result = ?
            WHERE user_id = ?
        """, (answers, test_result, user_id))
        await db.commit()


async def update_subscription_status(user_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users
            SET subscription_status = ?
            WHERE user_id = ?
        """, (status, user_id))
        await db.commit()


async def get_user_profile(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id,
                   full_name,
                   subscription_status,
                   test_result
            FROM users
            WHERE user_id = ?
        """, (user_id,)) as cursor:
            return await cursor.fetchone()


async def mark_coaching_eligible(user_id: int):
    """Record verified coaching entry and ensure an active ID, atomically.

    Only the guarded quiz-to-chat entry path may call this helper. It does not
    promote a user from chat history, quiz fields, or an existing session.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
            )
            await db.execute(
                "UPDATE users SET coaching_eligible = 1 WHERE user_id = ?",
                (user_id,),
            )
            await db.execute(
                "INSERT OR IGNORE INTO active_chat_sessions (user_id, conversation_id) "
                "VALUES (?, ?)",
                (user_id, uuid4().hex),
            )
            async with db.execute(
                "SELECT conversation_id FROM active_chat_sessions WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                conversation_id = (await cursor.fetchone())[0]
            await db.commit()
            return conversation_id
        except Exception:
            await db.rollback()
            raise


async def get_coaching_resume_conversation_id(user_id: int):
    """Read-only eligibility proof plus current session; never create an ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT s.conversation_id
            FROM users AS u
            JOIN active_chat_sessions AS s ON s.user_id = u.user_id
            WHERE u.user_id = ? AND u.coaching_eligible = 1
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


async def get_subscription_stats():
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total = (await cursor.fetchone())[0]

        async with db.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE subscription_status='SUBSCRIBED'
        """) as cursor:
            subs = (await cursor.fetchone())[0]

        async with db.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE subscription_status='UNSUBSCRIBED'
        """) as cursor:
            unsubs = (await cursor.fetchone())[0]

        return total, subs, unsubs


# --------------------------------------------------------------------
# Chat history
# --------------------------------------------------------------------

async def get_or_create_conversation_id(user_id: int):
    """DB identity survives FSM loss; never adopts NULL legacy messages."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("""
            INSERT OR IGNORE INTO active_chat_sessions (user_id, conversation_id)
            VALUES (?, ?)
        """, (user_id, uuid4().hex))
        async with db.execute("""
            SELECT conversation_id FROM active_chat_sessions WHERE user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
        await db.commit()
        return row[0]


async def is_active_conversation(user_id: int, conversation_id: str):
    if not conversation_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 1 FROM active_chat_sessions
            WHERE user_id = ? AND conversation_id = ?
        """, (user_id, conversation_id)) as cursor:
            return await cursor.fetchone() is not None


async def rotate_conversation(user_id: int, cutoff_chat_id: int, cutoff_message_id: int):
    """Rotate/delete atomically; an older private /new cannot undo a newer one."""
    if (
        type(cutoff_chat_id) is not int or cutoff_chat_id != user_id
        or type(cutoff_message_id) is not int or cutoff_message_id <= 0
    ):
        return None
    conversation_id = uuid4().hex
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute("""
                SELECT cutoff_chat_id, cutoff_message_id
                FROM active_chat_sessions WHERE user_id = ?
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
            if row is not None and (row[0] is not None or row[1] is not None):
                if row[0] != cutoff_chat_id or row[1] is None or cutoff_message_id <= row[1]:
                    await db.rollback()
                    return None
            await db.execute("""
                INSERT INTO active_chat_sessions
                (user_id, conversation_id, cutoff_chat_id, cutoff_message_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    conversation_id = excluded.conversation_id,
                    cutoff_chat_id = excluded.cutoff_chat_id,
                    cutoff_message_id = excluded.cutoff_message_id
            """, (user_id, conversation_id, cutoff_chat_id, cutoff_message_id))
            await db.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
            await db.execute(
                "DELETE FROM pending_drafts WHERE user_id = ? AND status = 'PENDING'",
                (user_id,),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return conversation_id


async def admit_user_message(user_id: int, full_name: str, username: str,
                             content: str, chat_id: int, message_id: int):
    """Atomically bind a private inbound turn to the DB session or reject it.

    Return (conversation_id, reason); a rejected turn never enters history.
    """
    if type(chat_id) is not int or chat_id != user_id or type(message_id) is not int or message_id <= 0:
        return None, "incomparable"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute("""
                INSERT OR IGNORE INTO active_chat_sessions (user_id, conversation_id)
                VALUES (?, ?)
            """, (user_id, uuid4().hex))
            async with db.execute("""
                SELECT conversation_id, cutoff_chat_id, cutoff_message_id
                FROM active_chat_sessions WHERE user_id = ?
            """, (user_id,)) as cursor:
                conversation_id, cutoff_chat_id, cutoff_message_id = await cursor.fetchone()
            if cutoff_chat_id is not None or cutoff_message_id is not None:
                if cutoff_chat_id != chat_id or cutoff_message_id is None:
                    await db.rollback()
                    return None, "incomparable"
                if message_id <= cutoff_message_id:
                    await db.rollback()
                    return None, "stale"
            await db.execute("""
                INSERT INTO chat_messages
                (user_id, full_name, username, role, content, conversation_id)
                VALUES (?, ?, ?, 'user', ?, ?)
            """, (user_id, full_name, username, content, conversation_id))
            await db.commit()
            return conversation_id, None
        except Exception:
            await db.rollback()
            raise


async def add_chat_message(user_id: int, full_name: str, username: str,
                           role: str, content: str, conversation_id: str):
    """Atomic active-ID check and insert; return False for stale work."""
    if not conversation_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            INSERT INTO chat_messages
            (user_id, full_name, username, role, content, conversation_id)
            SELECT ?, ?, ?, ?, ?, ?
            WHERE EXISTS (
                SELECT 1 FROM active_chat_sessions
                WHERE user_id = ? AND conversation_id = ?
            )
        """, (user_id, full_name, username, role, content, conversation_id,
              user_id, conversation_id))
        await db.commit()
        return cursor.rowcount == 1


async def get_recent_history(user_id: int, conversation_id: str, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT role, content FROM chat_messages
            WHERE user_id = ? AND conversation_id = ?
            ORDER BY id DESC LIMIT ?
        """, (user_id, conversation_id, limit)) as cursor:
            rows = await cursor.fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


async def get_conversation_history_with_ids(user_id: int, conversation_id: str):
    """Only rows belonging to the captured logical conversation."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, role, content FROM chat_messages
            WHERE user_id = ? AND conversation_id = ? ORDER BY id ASC
        """, (user_id, conversation_id)) as cursor:
            rows = await cursor.fetchall()
    return [{"id": row[0], "role": row[1], "content": row[2]} for row in rows]


async def create_pending_draft(user_id: int, full_name: str, user_message: str,
                               ai_draft: str, conversation_id: str):
    if not conversation_id:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            INSERT INTO pending_drafts
            (user_id, full_name, user_message, ai_draft, conversation_id)
            SELECT ?, ?, ?, ?, ?
            WHERE EXISTS (
                SELECT 1 FROM active_chat_sessions
                WHERE user_id = ? AND conversation_id = ?
            )
        """, (user_id, full_name, user_message, ai_draft, conversation_id,
              user_id, conversation_id))
        await db.commit()
        return cursor.lastrowid if cursor.rowcount == 1 else None


async def get_pending_draft(draft_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, user_id, full_name, user_message, ai_draft, status,
                   conversation_id
            FROM pending_drafts WHERE id = ?
        """, (draft_id,)) as cursor:
            return await cursor.fetchone()


async def is_pending_draft_active(draft_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 1 FROM pending_drafts AS d
            JOIN active_chat_sessions AS s
              ON s.user_id = d.user_id AND s.conversation_id = d.conversation_id
            WHERE d.id = ? AND d.status = 'PENDING'
        """, (draft_id,)) as cursor:
            return await cursor.fetchone() is not None


async def save_approved_draft_message(draft_id: int, username: str,
                                      content: str, status: str):
    """Atomic draft/session check, assistant insert, and draft status update."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            INSERT INTO chat_messages
            (user_id, full_name, username, role, content, conversation_id)
            SELECT d.user_id, d.full_name, ?, 'assistant', ?, d.conversation_id
            FROM pending_drafts AS d
            JOIN active_chat_sessions AS s
              ON s.user_id = d.user_id AND s.conversation_id = d.conversation_id
            WHERE d.id = ? AND d.status = 'PENDING'
        """, (username, content, draft_id))
        if cursor.rowcount != 1:
            await db.commit()
            return False
        await db.execute("""
            UPDATE pending_drafts SET status = ? WHERE id = ?
        """, (status, draft_id))
        await db.commit()
        return True


async def update_draft_status(draft_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE pending_drafts SET status = ? WHERE id = ?
        """, (status, draft_id))
        await db.commit()


# --------------------------------------------------------------------
# Channel CMS
# --------------------------------------------------------------------

async def save_channel_post(name: str, message_id: int, text: str):
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("""
            INSERT INTO channel_posts
            (name, message_id, text)
            VALUES (?, ?, ?)

            ON CONFLICT(name)
            DO UPDATE SET
                message_id = excluded.message_id,
                text = excluded.text,
                updated = CURRENT_TIMESTAMP
        """, (
            name,
            message_id,
            text
        ))

        await db.commit()


async def get_channel_post(name: str):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute("""
            SELECT message_id,
                   text
            FROM channel_posts
            WHERE name = ?
        """, (name,)) as cursor:

            return await cursor.fetchone()


async def get_post_names():
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute("""
            SELECT name
            FROM channel_posts
            ORDER BY name
        """) as cursor:

            rows = await cursor.fetchall()

        return [row[0] for row in rows]


# --------------------------------------------------------------------
# Placeholder functions
# --------------------------------------------------------------------

async def get_all_articles():
    return []


async def log_article_interaction(user_id: int,
                                  article_id: int,
                                  action: str):
    pass
