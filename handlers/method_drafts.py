from aiogram import Dispatcher, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services.knowledge import (
    get_method_drafts,
    create_method_asset,
    update_method_draft_status,
)


def register_method_drafts(
    dp: Dispatcher,
    admin_ids: list[int],
):

    @dp.message(F.text == "/метод_черновики")
    async def show_method_drafts(
        message: types.Message,
    ):

        if message.from_user.id not in admin_ids:
            return

        drafts = await get_method_drafts()

        if not drafts:
            await message.answer(
                "✨ Пока нет предложений метода от AI."
            )
            return

        for draft in drafts:

            (
                draft_id,
                proposal_id,
                suggested_type,
                suggested_title,
                suggested_content,
                suggested_questions,
                status,
                created_at,
            ) = draft

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Добавить в мой метод",
                            callback_data=f"draft_approve_{draft_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Отклонить",
                            callback_data=f"draft_reject_{draft_id}",
                        )
                    ],
                ]
            )

            await message.answer(
                (
                    f"✨ Предложение метода #{draft_id}\n\n"
                    f"Тип: {suggested_type}\n\n"
                    f"Название:\n{suggested_title}\n\n"
                    f"Описание:\n{suggested_content}\n\n"
                    f"Вопросы:\n{suggested_questions}"
                ),
                reply_markup=keyboard,
            )


    @dp.callback_query(
        F.data.startswith("draft_approve_")
    )
    async def approve_method_draft(
        callback: types.CallbackQuery,
    ):

        if callback.from_user.id not in admin_ids:
            return

        draft_id = int(
            callback.data.split("_")[-1]
        )

        drafts = await get_method_drafts()

        selected = None

        for draft in drafts:
            if draft[0] == draft_id:
                selected = draft
                break

        if not selected:
            await callback.answer(
                "Черновик не найден."
            )
            return

        (
            draft_id,
            proposal_id,
            suggested_type,
            suggested_title,
            suggested_content,
            suggested_questions,
            status,
            created_at,
        ) = selected

        await create_method_asset(
            proposal_id=proposal_id,
            asset_type=suggested_type,
            title=suggested_title,
            content=suggested_content,
        )

        await update_method_draft_status(
            draft_id,
            "APPROVED",
        )

        await callback.message.edit_text(
            callback.message.text
            + "\n\n✅ Добавлено в твой метод."
        )

        await callback.answer()
