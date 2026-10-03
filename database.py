import os
import aiosqlite

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

async def add_chat_message(user_id: int,
                           full_name: str,
                           username: str,
                           role: str,
                           content: str):

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO chat_messages
            (user_id, full_name, username, role, content)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, full_name, username, role, content))
        await db.commit()


async def get_recent_history(user_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute("""
            SELECT role, content
            FROM chat_messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit)) as cursor:

            rows = await cursor.fetchall()

        return [
            {
                "role": row[0],
                "content": row[1]
            }
            for row in reversed(rows)
        ]


# --------------------------------------------------------------------
# Pending drafts
# --------------------------------------------------------------------

async def create_pending_draft(user_id: int,
                               full_name: str,
                               user_message: str,
                               ai_draft: str):

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute("""
            INSERT INTO pending_drafts
            (user_id, full_name, user_message, ai_draft)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            full_name,
            user_message,
            ai_draft
        ))

        await db.commit()
        return cursor.lastrowid


async def get_pending_draft(draft_id: int):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute("""
            SELECT id,
                   user_id,
                   full_name,
                   user_message,
                   ai_draft,
                   status
            FROM pending_drafts
            WHERE id = ?
        """, (draft_id,)) as cursor:

            return await cursor.fetchone()


async def update_draft_status(draft_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("""
            UPDATE pending_drafts
            SET status = ?
            WHERE id = ?
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
