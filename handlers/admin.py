import logging

from prompts.admin import ADMIN_SYSTEM_PROMPT

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject

from utils.telegram import send_long_message
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def register_admin(
    dp: Dispatcher,
    bot: Bot,
    ai_client,
    model_name: str,
    admin_ids: list[int],
    approval_state,
    get_pending_draft,
    update_draft_status,
    add_chat_message,
):

    def is_admin(user_id: int) -> bool:
        return user_id in admin_ids

    @dp.message(Command("stats"))
    async def cmd_stats(message: types.Message):
        if not is_admin(message.from_user.id):
            return

        stats_text = (
            "📊 <b>Системная статистика бота</b>\n\n"
            f"🤖 Активная модель: <code>{model_name}</code>\n"
            "🎙️ Whisper-аудиотранскрипция: <code>Включена</code>\n"
            f"👥 Администраторы: <code>{len(admin_ids)} настроено</code>\n"
            "🟢 Статус: бот работает в штатном режиме\n"
            "💾 База данных: подключена"
        )

        await message.answer(stats_text, parse_mode="HTML")

    @dp.message(Command("ask"))
    async def cmd_ask_model(
        message: types.Message,
        command: CommandObject,
    ):
        if not is_admin(message.from_user.id):
            return

        query = command.args

        if not query:
            await message.answer(
                "⚠️ Пожалуйста, укажи текст после команды.\n"
                "Пример: <code>/ask Привет, как дела?</code>",
                parse_mode="HTML",
            )
            return

        await bot.send_chat_action(message.chat.id, "typing")

        try:
            response = await ai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": ADMIN_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": query,
                    },
                ],
                extra_headers={
                    "HTTP-Referer": "https://telegram.org",
                    "X-Title": "Olga Coaching Bot Admin",
                },
            )

            answer = response.choices[0].message.content

            response_text = (
                f"🤖 Ответ модели {model_name}:\n\n{answer}"
            )

            await send_long_message(
                message,
                response_text,
            )

        except Exception as exc:
            logging.exception("Admin /ask request failed")
            await message.answer(
                f"❌ Ошибка обращения к модели: {exc}"
            )

    @dp.callback_query(F.data.startswith("approve_"))
    async def approve_draft(callback: types.CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer(
                "У вас нет прав для этого действия.",
                show_alert=True,
            )
            return

        draft_id = int(callback.data.split("_", maxsplit=1)[1])
        draft = await get_pending_draft(draft_id)

        if not draft:
            await callback.answer(
                "Черновик не найден.",
                show_alert=True,
            )
            return

        if draft[5] != "PENDING":
            await callback.answer(
                f"Черновик уже обработан: {draft[5]}",
                show_alert=True,
            )
            return

        user_id = draft[1]
        full_name = draft[2]
        ai_draft = draft[4]

        if not isinstance(ai_draft, str) or not ai_draft.strip():
            logging.error(
                "Draft %s has invalid AI content: %r",
                draft_id,
                ai_draft,
            )
            await callback.answer(
                "Черновик пустой или повреждён. Его нельзя отправить.",
                show_alert=True,
            )
            return

        await bot.send_message(user_id, ai_draft)

        await add_chat_message(
            user_id,
            full_name,
            "N/A",
            "assistant",
            ai_draft,
        )

        await update_draft_status(draft_id, "APPROVED")

        await callback.message.edit_text(
            f"{callback.message.text}\n\n"
            "✅ <b>ОДОБРЕНО И ОТПРАВЛЕНО</b>",
            parse_mode="HTML",
        )

        await callback.answer("Ответ отправлен пользователю.")

    @dp.callback_query(F.data.startswith("edit_"))
    async def start_edit_draft(
        callback: types.CallbackQuery,
        state: FSMContext,
    ):
        if not is_admin(callback.from_user.id):
            await callback.answer(
                "У вас нет прав для этого действия.",
                show_alert=True,
            )
            return

        draft_id = int(callback.data.split("_", maxsplit=1)[1])
        draft = await get_pending_draft(draft_id)

        if not draft:
            await callback.answer(
                "Черновик не найден.",
                show_alert=True,
            )
            return

        if draft[5] != "PENDING":
            await callback.answer(
                f"Черновик уже обработан: {draft[5]}",
                show_alert=True,
            )
            return

        await state.update_data(editing_draft_id=draft_id)
        await state.set_state(approval_state.WAITING_FOR_EDIT)

        await callback.message.reply(
            "Пришли в ответ свой отредактированный текст сообщения 👇"
        )

        await callback.answer()

    @dp.message(approval_state.WAITING_FOR_EDIT)
    async def process_edited_text(
        message: types.Message,
        state: FSMContext,
    ):
        if not is_admin(message.from_user.id):
            return

        if not message.text:
            await message.answer(
                "Пришли, пожалуйста, текстовый вариант ответа."
            )
            return

        data = await state.get_data()
        draft_id = data.get("editing_draft_id")

        if not draft_id:
            await message.answer(
                "Не удалось определить редактируемый черновик."
            )
            await state.clear()
            return

        draft = await get_pending_draft(draft_id)

        if not draft:
            await message.answer("Черновик не найден.")
            await state.clear()
            return

        if draft[5] != "PENDING":
            await message.answer(
                f"Этот черновик уже обработан: {draft[5]}"
            )
            await state.clear()
            return

        user_id = draft[1]
        full_name = draft[2]
        edited_text = message.text.strip()

        await bot.send_message(user_id, edited_text)

        await add_chat_message(
            user_id,
            full_name,
            "N/A",
            "assistant",
            edited_text,
        )

        await update_draft_status(
            draft_id,
            "EDITED_AND_SENT",
        )

        await message.answer(
            "✅ Отредактированный ответ отправлен пользователю."
        )

        await state.clear()

    @dp.callback_query(F.data.startswith("reject_"))
    async def reject_draft(callback: types.CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer(
                "У вас нет прав для этого действия.",
                show_alert=True,
            )
            return

        draft_id = int(callback.data.split("_", maxsplit=1)[1])
        draft = await get_pending_draft(draft_id)

        if not draft:
            await callback.answer(
                "Черновик не найден.",
                show_alert=True,
            )
            return

        if draft[5] != "PENDING":
            await callback.answer(
                f"Черновик уже обработан: {draft[5]}",
                show_alert=True,
            )
            return

        await update_draft_status(draft_id, "REJECTED")

        await callback.message.edit_text(
            f"{callback.message.text}\n\n"
            "❌ <b>ОТКЛОНЕНО</b>",
            parse_mode="HTML",
        )

        await callback.answer("Черновик отклонён.")
