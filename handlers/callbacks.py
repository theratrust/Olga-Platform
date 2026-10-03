from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def register_callbacks(
    dp: Dispatcher,
    bot,
    state_cls,
):

    @dp.callback_query(F.data == "menu_learn_more")
    async def menu_learn_more_handler(callback: types.CallbackQuery):
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
                        text="👉 Задать вопрос Ольге",
                        callback_data="open_ai_chat",
                    )
                ]
            ]
        )

        await bot.send_message(
            chat_id=chat_id,
            text=learn_more_text,
            reply_markup=kb_learn,
            parse_mode="HTML",
        )

    @dp.callback_query(F.data == "open_ai_chat")
    async def enter_chat(callback: types.CallbackQuery, state: FSMContext):
        await callback.answer()

        current_state = await state.get_state()

        if current_state == state_cls.AI_CHAT.state:
            return

        await callback.message.answer(
            "Напиши своё сообщение ниже, и я отвечу тебе лично 👇"
        )

        await state.set_state(state_cls.AI_CHAT)
