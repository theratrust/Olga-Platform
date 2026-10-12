import logging

from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.conversation_admission import is_private_coaching_chat


def register_callbacks(
    dp: Dispatcher,
    bot,
    state_cls,
    mark_coaching_eligible=None,
    get_coaching_resume_conversation_id=None,
):

    async def reject(callback, reason):
        logging.info("quiz_callback_rejected reason=%s", reason)
        await callback.answer("Эта кнопка больше не активна.", show_alert=True)

    def matches_entry_message(data, message):
        expected_id = data.get("quiz_entry_message_id")
        return (
            type(expected_id) is int
            and expected_id > 0
            and expected_id == message.message_id
        )

    @dp.callback_query(F.data == "continue_coaching")
    async def continue_coaching(callback: types.CallbackQuery, state: FSMContext):
        if not is_private_coaching_chat(callback.message.chat, callback.from_user.id):
            await callback.answer()
            return
        home_state = getattr(getattr(state_cls, "HOME", None), "state", None)
        if home_state is None or await state.get_state() != home_state:
            await reject(callback, "wrong_state")
            return
        data = await state.get_data()
        expected_id = data.get("home_message_id")
        if (
            type(expected_id) is not int
            or expected_id <= 0
            or expected_id != callback.message.message_id
        ):
            await reject(callback, "stale_message")
            return
        # Recheck durable authority at the action, not just when home was shown.
        conversation_id = (
            await get_coaching_resume_conversation_id(callback.from_user.id)
            if get_coaching_resume_conversation_id is not None else None
        )
        if conversation_id is None:
            await reject(callback, "missing_session")
            return
        await callback.answer()
        await state.update_data(
            home_message_id=None, shadow_conversation_id=conversation_id,
        )
        await state.set_state(state_cls.AI_CHAT)
        await callback.message.answer(
            "Можешь продолжить разговор. Напиши, что сейчас для тебя важно."
        )

    @dp.callback_query(F.data == "menu_learn_more")
    async def menu_learn_more_handler(callback: types.CallbackQuery, state: FSMContext):
        if not is_private_coaching_chat(callback.message.chat, callback.from_user.id):
            await callback.answer()
            return
        if await state.get_state() != state_cls.CALC.state:
            await reject(callback, "wrong_state")
            return
        data = await state.get_data()
        if not matches_entry_message(data, callback.message):
            await reject(callback, "stale_message")
            return
        await callback.answer()
        chat_id = callback.message.chat.id

        learn_more_text = (
            "Я надеюсь, что этот экспресс-тест помог тебе лучше понять то, "
            "что происходит с тобой прямо сейчас. 🌱\n\n"
            "А теперь я предлагаю заглянуть немного глубже.\n\n"
            "❓ Почему ты оказалась именно в этой точке?\n"
            "❓ Что повлияло на то, как ты чувствуешь себя сегодня?\n\n"
            "Когда мы пытаемся понять, почему нам тяжело, мы естественным образом "
            "ищем ответы во внешних обстоятельствах.\n\n"
            "Переезд в другую страну вслед за партнёром — это всегда масштабная "
            "трансформация.\n\n"
            "Вместе с географией меняется и наша внутренняя реальность. 🌍\n\n"
            "Привычные опоры могут пошатнуться, круг общения — исчезнуть, "
            "а чувство самостоятельности смениться чувством зависимости.\n\n"
            "Часто кажется, что наше состояние напрямую зависит от внешних факторов: "
            "языкового барьера, культурного шока или необходимости заново искать "
            "своё место в мире.\n\n"
            "И это действительно так. Эти факторы влияют на нас.\n\n"
            "Но есть ещё один важный фактор, который часто ускользает от нашего "
            "внимания, хотя именно он во многом определяет, как проходит период адаптации.\n\n"
            "Речь о том, что происходит в нашем внутреннем мире: как мы воспринимаем происходящее.\n\n"
            "И, самое главное — кем мы видим себя в этой новой реальности и что думаем о себе.\n\n"
            "Именно поэтому сейчас важно замедлиться и честно ответить себе на несколько вопросов:\n\n"
            "🔹 Что ты говоришь себе о себе?\n"
            "🔹 Веришь ли ты в свои силы или сомневаешься в них?\n"
            "🔹 Кем ты видишь себя в этой новой жизни?\n"
            "🔹 Принимаешь ли ты себя такой, какая ты есть сегодня?\n\n"
            "🔍 Обрати внимание, как ты разговариваешь с собой.\n\n"
            "С поддержкой и принятием — или чаще через сомнения и критику?\n\n"
            "Твой мир вокруг — это зеркало твоих ежедневных мыслей о себе.\n\n"
            "Представь, как могла бы измениться твоя жизнь, если бы ты..."
        )

        kb_learn = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👉 Задать вопрос",
                        callback_data="open_ai_chat",
                    )
                ]
            ]
        )

        sent = await bot.send_message(
            chat_id=chat_id,
            text=learn_more_text,
            reply_markup=kb_learn,
            parse_mode="HTML",
        )
        await state.update_data(quiz_entry_message_id=sent.message_id)

    @dp.callback_query(F.data == "open_ai_chat")
    async def enter_chat(callback: types.CallbackQuery, state: FSMContext):
        if not is_private_coaching_chat(callback.message.chat, callback.from_user.id):
            await callback.answer()
            return
        current_state = await state.get_state()
        if current_state != state_cls.CALC.state:
            await reject(callback, "wrong_state")
            return

        data = await state.get_data()
        if not matches_entry_message(data, callback.message):
            await reject(callback, "stale_message")
            return
        questions = data.get("quiz_questions")
        answers = data.get("answers_list")
        verified_entry = (
            isinstance(questions, list) and bool(questions)
            and isinstance(answers, list) and len(answers) == len(questions)
            and data.get("current_q_idx") == len(questions)
            and data.get("archetype") in {"Свет", "Полутень", "Тень"}
            and data.get("result_processing_message_id") is None
        )
        if not verified_entry:
            await reject(callback, "invalid_value")
            return

        await callback.answer()
        if mark_coaching_eligible is not None:
            conversation_id = await mark_coaching_eligible(callback.from_user.id)
            await state.update_data(shadow_conversation_id=conversation_id)
        await state.update_data(quiz_entry_message_id=None)
        await state.set_state(state_cls.AI_CHAT)
        await callback.message.answer(
            "Напиши своё сообщение ниже — AI-ассистент ответит, следуя методу Ольги 👇"
        )
