import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.coaching_generator import build_system_instruction, build_messages, generate_candidate
from utils.telegram import split_long_text


def register_chat(
    dp: Dispatcher,
    bot: Bot,
    ai_client,
    model_name: str,
    admin_ids: list[int],
    state_cls,
    get_user_display_name,
    get_user_first_name,
    add_chat_message,
    get_recent_history,
    create_pending_draft,
    clear_chat_history,
    direct_chat: bool = False,
    shadow_observer=None,
    quality_shadow_observer=None,
):

    @dp.message(Command("new"))
    async def cmd_new(
        message: types.Message,
        state: FSMContext,
    ):
        user_id = message.from_user.id

        await clear_chat_history(user_id)
        await state.set_state(state_cls.AI_CHAT)
        await state.update_data(shadow_conversation_id=uuid4().hex)

        await message.answer(
            "Начинаем новый разговор. Предыдущая история очищена.\n\n"
            "Напиши, что сейчас для тебя важно."
        )

    async def ai_chat_handler(
        message: types.Message,
        state: FSMContext,
    ):
        user_id = message.from_user.id

        current_state = await state.get_state()
        if current_state != state_cls.AI_CHAT.state:
            return

        user_text = message.text
        full_name = get_user_display_name(message.from_user)
        first_name = get_user_first_name(message.from_user)
        username = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else "без username"
        )

        await bot.send_chat_action(message.chat.id, "typing")

        await add_chat_message(
            user_id,
            full_name,
            username,
            "user",
            user_text,
        )

        data = await state.get_data()
        archetype = data.get("archetype", "Полутень")
        # FSM-only correlation; never enters the prompt, database or user messages.
        conversation_id = data.get("shadow_conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            conversation_id = uuid4().hex
            await state.update_data(shadow_conversation_id=conversation_id)

        system_instruction = build_system_instruction(
            first_name=first_name,
            archetype=archetype,
        )

        history = await get_recent_history(user_id, limit=20)

        messages_payload = build_messages(system_instruction, history)

        await message.answer(
            f"Спасибо за твой вопрос, {first_name}! "
            "Я сейчас обдумываю ответ и скоро напишу тебе... 🌺"
        )

        logging.info(
            f"User acknowledgement sent to {user_id}"
        )

        try:
            ai_draft = await generate_candidate(ai_client, model_name, messages_payload)
            logging.info(
                "OpenRouter response received for user %s via model %s",
                user_id,
                model_name,
            )

            if direct_chat:
                await bot.send_message(user_id, ai_draft)

                await add_chat_message(
                    user_id,
                    full_name,
                    username,
                    "assistant",
                    ai_draft,
                )

                logging.info(
                    "Direct chat response sent to user %s",
                    user_id,
                )

            else:
                draft_id = await create_pending_draft(
                    user_id,
                    full_name,
                    user_text,
                    ai_draft,
                )

                logging.info(
                    f"Draft {draft_id} created for user {user_id}"
                )

                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Одобрить",
                                callback_data=f"approve_{draft_id}",
                            ),
                            InlineKeyboardButton(
                                text="✏️ Изменить",
                                callback_data=f"edit_{draft_id}",
                            ),
                            InlineKeyboardButton(
                                text="❌ Отклонить",
                                callback_data=f"reject_{draft_id}",
                            ),
                        ]
                    ]
                )

                mod_text = (
                    "📩 Новый вопрос от пользователя: "
                    f"{full_name} ({username})\n"
                    f"«{user_text}»\n\n"
                    f"🤖 Черновик от {model_name} "
                    f"({archetype}):\n"
                    f"{ai_draft}"
                )

                for admin_id in admin_ids:
                    try:
                        chunks = split_long_text(mod_text)

                        for index, chunk in enumerate(chunks):
                            is_last_chunk = index == len(chunks) - 1

                            await bot.send_message(
                                admin_id,
                                chunk,
                                reply_markup=kb if is_last_chunk else None,
                            )

                        logging.info(
                            f"Draft {draft_id} sent to admin "
                            f"{admin_id}"
                        )

                    except Exception as exc:
                        logging.error(
                            f"Failed to send draft {draft_id} "
                            f"to admin {admin_id}: {exc}"
                        )

            # Observation is scheduled only after the existing delivery path completes.
            # It never awaits an evaluator or changes the candidate/route.
            if shadow_observer is not None:
                try:
                    shadow_observer(history, user_text, ai_draft, session_id=conversation_id)
                except Exception:
                    logging.error("SHADOW_EVAL_FAIL post_delivery_hook_error")

            if quality_shadow_observer is not None:
                try:
                    quality_shadow_observer(history, user_text, ai_draft, session_id=conversation_id)
                except Exception:
                    try:
                        logging.error("QUALITY_SHADOW_EVAL_FAIL %s", json.dumps({
                            "event": "QUALITY_SHADOW_EVAL_FAIL",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "mode": "quality_shadow",
                            "evaluator_error_kind": "post_delivery_hook_error",
                        }))
                    except Exception:
                        pass

        except Exception as exc:
            logging.exception(
                f"OpenRouter error: {exc}"
            )

            await message.answer(
                "Произошла ошибка связи. "
                "Попробуй написать ещё раз."
            )

    dp.message.register(
        ai_chat_handler,
        F.text & ~F.text.startswith("/"),
    )

    return ai_chat_handler
