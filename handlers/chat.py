import json
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.coaching_generator import build_system_instruction, build_messages, generate_candidate
from services.conversation_state import build_carry_forward, render_runtime_memory
from services.conversation_admission import admission_lock, private_message_marker
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
    rotate_conversation,
    get_or_create_conversation_id,
    is_active_conversation,
    direct_chat: bool = False,
    shadow_observer=None,
    quality_shadow_observer=None,
    get_conversation_history_with_ids=None,
    admit_user_message=None,
):
    if admit_user_message is None:
        raise ValueError("Atomic user admission is required")

    @dp.message(Command("new"))
    async def cmd_new(
        message: types.Message,
        state: FSMContext,
    ):
        marker = private_message_marker(message)
        if marker is None:
            # Non-private coaching commands are ignored without changing FSM or DB.
            logging.info("ADMISSION_REJECTED_INCOMPARABLE operation=new")
            return
        user_id = message.from_user.id
        async with admission_lock(user_id):
            conversation_id = await rotate_conversation(user_id, *marker)
            if conversation_id is None:
                logging.info("ADMISSION_REJECTED_STALE operation=new")
                return
            await state.set_state(state_cls.AI_CHAT)
            await state.update_data(shadow_conversation_id=conversation_id)

        await message.answer(
            "Начинаем новый разговор. Предыдущая история очищена.\n\n"
            "Напиши, что сейчас для тебя важно."
        )

    async def ai_chat_handler(
        message: types.Message,
        state: FSMContext,
    ):
        marker = private_message_marker(message)
        if marker is None:
            logging.info("ADMISSION_REJECTED_INCOMPARABLE operation=user")
            return
        user_id = message.from_user.id
        user_text = message.text
        full_name = get_user_display_name(message.from_user)
        first_name = get_user_first_name(message.from_user)
        username = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else "без username"
        )

        async with admission_lock(user_id):
            current_state = await state.get_state()
            if current_state != state_cls.AI_CHAT.state:
                return
            conversation_id, rejection = await admit_user_message(
                user_id, full_name, username, user_text, *marker,
            )
            if conversation_id is None:
                event = "ADMISSION_REJECTED_STALE" if rejection == "stale" else "ADMISSION_REJECTED_INCOMPARABLE"
                logging.info("%s operation=user", event)
                return

        await bot.send_chat_action(message.chat.id, "typing")

        data = await state.get_data()
        archetype = data.get("archetype", "Полутень")
        # FSM is only an observer cache; DB identity governs persistence.
        if data.get("shadow_conversation_id") != conversation_id:
            await state.update_data(shadow_conversation_id=conversation_id)

        system_instruction = build_system_instruction(
            first_name=first_name,
            archetype=archetype,
        )

        history = await get_recent_history(user_id, conversation_id, limit=20)

        ledger = []
        if get_conversation_history_with_ids is not None:
            try:
                source_rows = await get_conversation_history_with_ids(user_id, conversation_id)
                ledger = build_carry_forward(source_rows, history)
            except Exception:
                logging.warning("Conversation memory unavailable; using recent history")
        runtime_memory = render_runtime_memory(ledger)
        logging.debug(
            "Conversation memory item_count=%d event_types=%s injected=%s",
            len(ledger),
            sorted({item["event_type"] for item in ledger}),
            bool(runtime_memory),
        )
        messages_payload = build_messages(
            system_instruction, history, runtime_memory=runtime_memory
        )

        await message.answer(
            f"Спасибо за твой вопрос, {first_name}! "
            "Я сейчас обдумываю ответ и скоро напишу тебе... 🌺"
        )

        logging.info("User acknowledgement sent")

        try:
            ai_draft = await generate_candidate(ai_client, model_name, messages_payload)
            logging.info("OpenRouter response received")

            if not await is_active_conversation(user_id, conversation_id):
                logging.info("Conversation stale_write_rejected operation=generated_response")
                return

            if direct_chat:
                await bot.send_message(user_id, ai_draft)

                saved = await add_chat_message(
                    user_id,
                    full_name,
                    username,
                    "assistant",
                    ai_draft,
                    conversation_id,
                )
                if not saved:
                    logging.info("Conversation stale_write_rejected operation=assistant")
                    return

                logging.info("Direct chat response sent")

            else:
                draft_id = await create_pending_draft(
                    user_id,
                    full_name,
                    user_text,
                    ai_draft,
                    conversation_id,
                )
                if draft_id is None:
                    logging.info("Conversation stale_write_rejected operation=draft")
                    return

                logging.info("Moderation draft created")

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

                        logging.info("Moderation draft sent to admin")

                    except Exception as exc:
                        logging.error("Moderation draft delivery failed kind=%s", type(exc).__name__)

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
            logging.error("OpenRouter error kind=%s", type(exc).__name__)

            await message.answer(
                "Произошла ошибка связи. "
                "Попробуй написать ещё раз."
            )

    dp.message.register(
        ai_chat_handler,
        F.text & ~F.text.startswith("/"),
    )

    return ai_chat_handler
