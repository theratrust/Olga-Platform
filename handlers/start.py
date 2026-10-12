from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.conversation_admission import is_private_coaching_chat


def register_start(
    dp: Dispatcher,
    get_user_first_name,
    get_image_file,
    state_cls=None,
    is_coaching_eligible=None,
):

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message, state: FSMContext):
        if not is_private_coaching_chat(message.chat, message.from_user.id):
            return

        # /start is navigation. Only the explicit durable marker can select home.
        eligible = (
            await is_coaching_eligible(message.from_user.id)
            if is_coaching_eligible is not None else False
        )
        await state.clear()
        if eligible:
            if state_cls is None:
                raise ValueError("A home FSM state is required for eligible users")
            await state.set_state(state_cls.HOME)
            home = await message.answer(
                "С возвращением. Ты можешь продолжить текущий разговор.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text="Продолжить разговор", callback_data="continue_coaching",
                )]]),
            )
            await state.update_data(home_message_id=home.message_id)
            return

        user_first_name = get_user_first_name(message.from_user)

        await state.update_data(
            user_first_name=user_first_name
        )

        caption = (
            f"Здравствуй, {user_first_name}! ✨\n\n"
            "Ты здесь — значит, пришло время поговорить о самом важном.\n\n"
            "О тебе. 💜\n\n"
            "Переезд в другую страну — это всегда прыжок в неизвестность. "
            "Особенно когда этот шаг продиктован любовью и желанием быть рядом с близким человеком.\n\n"
            "Даже если решение было осознанным и желанным, внутри может накопиться много вопросов.\n\n"
            "Это пространство создано для того, чтобы ты могла остановиться, выдохнуть и снова услышать себя. 🌺\n\n"
            "Давай посмотрим, насколько гармонично проходит твоя адаптация. 👇"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Пройти экспресс-тест (2 мин)",
                        callback_data="start_quiz",
                    )
                ]
            ]
        )

        welcome = await message.answer_photo(
            photo=get_image_file("q1_welcome.jpg"),
            caption=caption,
            reply_markup=kb,
            parse_mode="HTML",
        )
        await state.update_data(welcome_message_id=welcome.message_id)
