async def get_recent_knowledge_proposals(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT
                id,
                category,
                title,
                content,
                status,
                created_at
            FROM knowledge_proposals
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:

            return await cursor.fetchall()
