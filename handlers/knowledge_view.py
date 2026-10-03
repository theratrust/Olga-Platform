from aiogram import Dispatcher, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services.knowledge import (
    get_recent_knowledge_proposals,
    update_knowledge_proposal_status,
    create_method_draft,
)

from services.method_ai import enrich_method_observation
from services.method_parser import parse_method_ai_response


def register_knowledge_view(
    dp: Dispatcher,
    admin_ids: list[int],
    ai_client,
    model_name,
):

    @dp.message(F.text == "/мои_знания")
    async def my_knowledge(
        message: types.Message,
    ):

        if message.from_user.id not in admin_ids:
            return

        proposals = await get_recent_knowledge_proposals()

        if not proposals:
            await message.answer(
                "📚 Пока в твоём методе нет сохранённых материалов."
            )
            return

        for item in proposals:

            (
                proposal_id,
                category,
                title,
                content,
                status,
                created_at,
                knowledge_type,
            ) = item

            kb = None

            if status == "PENDING":
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Сохранить в метод",
                                callback_data=f"knowledge_approve_{proposal_id}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="❌ Отклонить",
                                callback_data=f"knowledge_reject_{proposal_id}",
                            )
                        ],
                    ]
                )

            await message.answer(
                (
                    f"#{proposal_id}\n\n"
                    f"📝 {content[:500]}\n\n"
                    f"Тип: {knowledge_type}\n"
                    f"Статус: {status}"
                ),
                reply_markup=kb,
            )


    @dp.callback_query(
        F.data.startswith("knowledge_approve_")
    )
    async def approve_knowledge(
        callback: types.CallbackQuery,
    ):

        if callback.from_user.id not in admin_ids:
            await callback.answer(
                "Нет доступа.",
                show_alert=True,
            )
            return

        proposal_id = int(
            callback.data.split("_")[-1]
        )

        ai_result = await enrich_method_observation(
            ai_client,
            model_name,
            callback.message.text,
        )

        parsed = parse_method_ai_response(
            ai_result
        )

        await create_method_draft(
            proposal_id=proposal_id,
            suggested_type=parsed["type"],
            suggested_title=parsed["title"],
            suggested_content=parsed["principle"],
            suggested_questions="\n".join(
                parsed["questions"]
            ),
        )

        await update_knowledge_proposal_status(
            proposal_id,
            "APPROVED",
            str(callback.from_user.id),
        )

        await callback.message.edit_text(
            callback.message.text.replace(
                "Статус: PENDING",
                "Статус: APPROVED"
            )
            + "\n\n✅ Добавлено в твой метод."
        )

        await callback.answer()


    @dp.callback_query(
        F.data.startswith("knowledge_reject_")
    )
    async def reject_knowledge(
        callback: types.CallbackQuery,
    ):

        if callback.from_user.id not in admin_ids:
            await callback.answer(
                "Нет доступа.",
                show_alert=True,
            )
            return

        proposal_id = int(
            callback.data.split("_")[-1]
        )

        await update_knowledge_proposal_status(
            proposal_id,
            "REJECTED",
            str(callback.from_user.id),
        )

        await callback.message.edit_text(
            callback.message.text
            + "\n\n❌ Отклонено."
        )

        await callback.answer()
