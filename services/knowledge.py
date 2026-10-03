import aiosqlite
from database import DB_PATH


async def create_knowledge_proposal(
    source_type: str,
    source_name: str,
    category: str,
    title: str,
    content: str,
    knowledge_type: str = "observation",
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO knowledge_proposals
            (
                source_type,
                source_name,
                category,
                title,
                content,
                knowledge_type
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_type,
                source_name,
                category,
                title,
                content,
                knowledge_type,
            ),
        )

        await db.commit()

        return cursor.lastrowid

async def get_knowledge_proposal(
    proposal_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT
                id,
                source_type,
                source_name,
                category,
                title,
                content,
                status
            FROM knowledge_proposals
            WHERE id = ?
            """,
            (proposal_id,),
        ) as cursor:

            return await cursor.fetchone()

async def get_pending_knowledge_proposals():
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT
                id,
                source_type,
                source_name,
                category,
                title,
                content,
                status
            FROM knowledge_proposals
            WHERE status = 'PENDING'
            ORDER BY created_at DESC
            """
        ) as cursor:

            return await cursor.fetchall()


async def update_knowledge_proposal_status(
    proposal_id: int,
    status: str,
    approved_by: str | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            UPDATE knowledge_proposals
            SET
                status = ?,
                approved_by = ?,
                approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                approved_by,
                proposal_id,
            ),
        )

        await db.commit()


async def get_recent_knowledge_proposals(
    limit: int = 10,
):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT
                id,
                category,
                title,
                content,
                status,
                created_at,
                knowledge_type
            FROM knowledge_proposals
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:

            return await cursor.fetchall()
async def create_method_asset(
    proposal_id: int,
    asset_type: str,
    title: str,
    content: str,
):
    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            INSERT INTO method_assets
            (
                proposal_id,
                asset_type,
                title,
                content,
                version,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                asset_type,
                title,
                content,
                "1.0",
                "ACTIVE",
            ),
        )

        await db.commit()

        return cursor.lastrowid


async def create_method_draft(
    proposal_id: int,
    suggested_type: str,
    suggested_title: str,
    suggested_content: str,
    suggested_questions: str,
):
    async with aiosqlite.connect(DB_PATH) as db:

        existing = await db.execute(
            """
            SELECT id
            FROM method_drafts
            WHERE proposal_id = ?
            AND status = 'PENDING'
            """,
            (proposal_id,),
        )

        row = await existing.fetchone()

        if row:
            return row[0]

        cursor = await db.execute(
            """
            INSERT INTO method_drafts
            (
                proposal_id,
                suggested_type,
                suggested_title,
                suggested_content,
                suggested_questions
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                suggested_type,
                suggested_title,
                suggested_content,
                suggested_questions,
            ),
        )

        await db.commit()

        return cursor.lastrowid


async def get_method_drafts(
    limit: int = 10,
):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT
                id,
                proposal_id,
                suggested_type,
                suggested_title,
                suggested_content,
                suggested_questions,
                status,
                created_at
            FROM method_drafts
            WHERE status = 'PENDING'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:

            return await cursor.fetchall()


async def get_method_assets(
    limit: int = 20,
):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT
                id,
                proposal_id,
                asset_type,
                title,
                content,
                version,
                created_at
            FROM method_assets
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:

            return await cursor.fetchall()


async def update_method_draft_status(
    draft_id: int,
    status: str,
):
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            UPDATE method_drafts
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                draft_id,
            ),
        )

        await db.commit()
