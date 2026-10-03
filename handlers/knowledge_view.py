from aiogram import Dispatcher, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services.knowledge import (
    get_recent_knowledge_proposals,
    get_knowledge_proposal,
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
                "📚 Пока нет сохранённых материалов для метода."
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
                                text="🧩 Подтвердить и создать AI-черновик",
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

        proposal = await get_knowledge_proposal(
            proposal_id
        )

        if not proposal:
            await callback.answer(
                "Исходный материал не найден.",
                show_alert=True,
            )
            return

        (
            stored_id,
            source_type,
            source_name,
            category,
            title,
            content,
            status,
        ) = proposal

        if status != "PENDING":
            await callback.answer(
                f"Материал уже обработан: {status}",
                show_alert=True,
            )
            return

        ai_result = await enrich_method_observation(
            ai_client,
            model_name,
            content,
        )

        parsed = parse_method_ai_response(
            ai_result
        )

        questions = parsed["questions"]

        if isinstance(questions, list):
            suggested_questions = "\n".join(
                str(question)
                for question in questions
            )
        else:
            suggested_questions = str(questions or "")

        await create_method_draft(
            proposal_id=proposal_id,
            suggested_type=parsed["type"],
            suggested_title=parsed["title"],
            suggested_content=parsed["principle"],
            suggested_questions=suggested_questions,
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
            + (
                "\n\n✅ Исходный материал подтверждён."
                "\n"
                "AI создал черновик структуры метода."
                "\n"
                "Он ещё не является частью метода."
                "\n"
                "Проверь его через /метод_черновики."
            )
        )

        await callback.answer(
            "AI-черновик создан."
        )

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

        proposal = await get_knowledge_proposal(
            proposal_id
        )

        if not proposal:
            await callback.answer(
                "Материал не найден.",
                show_alert=True,
            )
            return

        if proposal[6] != "PENDING":
            await callback.answer(
                f"Материал уже обработан: {proposal[6]}",
                show_alert=True,
            )
            return

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
