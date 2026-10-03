import asyncio
import aiosqlite
import os
import json

DB = os.getenv("DB_NAME", "dev_bot.db")


async def main():
    async with aiosqlite.connect(DB) as db:

        await db.execute("""
        CREATE TABLE IF NOT EXISTS telegram_pages(
            slug TEXT PRIMARY KEY,
            chat_id INTEGER,
            message_id INTEGER,
            photo_file_id TEXT,
            caption TEXT,
            keyboard_json TEXT,
            updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        keyboard = json.dumps([
            [
                {
                    "text": "🧩 Пройти экспресс-тест (2 мин)",
                    "callback": "start_quiz"
                }
            ]
        ])

        await db.execute("""
        INSERT OR REPLACE INTO telegram_pages
        (
            slug,
            chat_id,
            message_id,
            photo_file_id,
            caption,
            keyboard_json
        )
        VALUES
        (
            ?,?,?,?,?,?
        )
        """,
        (
            "welcome",
            -1001234567890,          # placeholder
            1,                       # placeholder
            "PHOTO_FILE_ID",         # placeholder
            """👋 Здравствуйте!

Я Ольга.

Рада видеть вас здесь.""",
            keyboard
        ))

        await db.commit()

    print("telegram_pages initialized")


asyncio.run(main())
