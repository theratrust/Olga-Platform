from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile


def register_start(
    dp: Dispatcher,
    get_user_first_name,
    get_image_file,
):

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message, state: FSMContext):

        await state.clear()

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

        await message.answer_photo(
            photo=get_image_file("q1_welcome.jpg"),
            caption=caption,
            reply_markup=kb,
            parse_mode="HTML",
        )
