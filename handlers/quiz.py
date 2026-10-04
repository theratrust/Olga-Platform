import asyncio

from aiogram import Dispatcher, Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def register_quiz(
    dp: Dispatcher,
    bot: Bot,
    state_cls,
    default_questions,
    get_user_first_name,
    get_image_file,
):

    async def render_question_step(
        message_obj: types.Message,
        state: FSMContext,
        delete_previous: bool = False,
    ):
        data = await state.get_data()

        questions = data.get("quiz_questions", default_questions)
        idx = data.get("current_q_idx", 0)
        user_first_name = data.get("user_first_name", "Гостья")
        chat_id = message_obj.chat.id

        if delete_previous:
            try:
                await message_obj.delete()
            except Exception:
                pass

        if idx >= len(questions):

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Узнать мой результат",
                            callback_data="show_result",
                        )
                    ]
                ]
            )

            text = (
                f"Благодарю тебя за честность, {user_first_name}! 💙\n\n"
                "Пройти этот тест до конца — это уже большой и смелый шаг навстречу себе.\n\n"
                "Я соединила все твои ответы в единую картину.\n\n"
                "Давай посмотрим, что она говорит о твоей текущей ситуации. 👇"
            )

            sent = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
            )

            await state.update_data(
                last_question_message_id=sent.message_id
            )

            await state.set_state(state_cls.CALC)

            return

        q = questions[idx]

        rows = []

        for i, option in enumerate(q["options"]):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=option["text"],
                        callback_data=f"q_ans_{i}",
                    )
                ]
            )

        sent = await bot.send_message(
            chat_id=chat_id,
            text=q["question_text"],
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=rows
            ),
            parse_mode="HTML",
        )

        await state.update_data(
            last_question_message_id=sent.message_id
        )

        await state.set_state(state_cls.QUESTION_STEP)

    @dp.callback_query(F.data == "start_quiz")
    async def start_quiz(
        callback: types.CallbackQuery,
        state: FSMContext,
    ):
        await callback.answer()

        try:
            await callback.message.delete()
        except Exception:
            logging.exception("Failed to delete welcome message")

        name = get_user_first_name(callback.from_user)

        await state.update_data(
            quiz_questions=default_questions,
            current_q_idx=0,
            total_score=0,
            user_first_name=name,
            answers_list=[],
        )

        await render_question_step(
            callback.message,
            state,
            delete_previous=False,
        )

    @dp.callback_query(F.data.startswith("q_ans_"))
    async def process_answer(
        callback: types.CallbackQuery,
        state: FSMContext,
    ):
        await callback.answer()

        try:
            await bot.send_chat_action(
                callback.message.chat.id,
                "typing",
            )
        except Exception:
            pass

        await asyncio.sleep(2)

        option_index = int(callback.data.split("_")[2])

        data = await state.get_data()

        questions = data.get(
            "quiz_questions",
            default_questions,
        )

        idx = data.get("current_q_idx", 0)

        current_score = data.get(
            "total_score",
            0,
        )

        if idx >= len(questions):
            await callback.answer(
                "Этот вопрос уже завершён. Начни тест заново через /start.",
                show_alert=True,
            )
            return

        if option_index < 0 or option_index >= len(questions[idx]["options"]):
            await callback.answer(
                "Этот вариант ответа больше недоступен. Начни тест заново через /start.",
                show_alert=True,
            )
            return

        option = questions[idx]["options"][option_index]

        answers = data.get("answers_list", [])

        answers.append(
            {
                "q": idx + 1,
                "choice": option["text"],
                "score": option["score"],
            }
        )

        await state.update_data(
            total_score=current_score + option["score"],
            current_q_idx=idx + 1,
            answers_list=answers,
        )

        await render_question_step(
            callback.message,
            state,
            delete_previous=True,
        )

    @dp.callback_query(state_cls.CALC, F.data == "show_result")
    async def show_result(
        callback: types.CallbackQuery,
        state: FSMContext,
    ):
        await callback.answer()

        try:
            await callback.message.delete()
        except Exception:
            pass

        try:
            await bot.send_chat_action(
                callback.message.chat.id,
                "upload_photo",
            )
        except Exception:
            pass

        await asyncio.sleep(5)

        data = await state.get_data()

        total = data.get("total_score", 0)

        name = get_user_first_name(
            callback.from_user
        )

        if total == 0:
            archetype = "Свет"
            filename = "svet.jpg"
            desc = (
                "Ты сохраняешь контакт с собой "
                "и продолжаешь строить свою жизнь, "
                "оставаясь её автором."
            )

        elif total < 4:
            archetype = "Полутень"
            filename = "poluten.jpg"
            desc = (
                "Сейчас ты можешь находиться "
                "в состоянии перехода."
            )

        else:
            archetype = "Тень"
            filename = "ten.jpg"
            desc = (
                "Сейчас важно снова обратить "
                "внимание на себя."
            )

        await state.update_data(
            archetype=archetype
        )

        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=get_image_file(filename),
            caption=(
                f"{name}, спасибо за твое доверие.\n\n"
                f"🌓 <b>Твой результат — {archetype}</b>\n\n"
                f"{desc}"
            ),
            parse_mode="HTML",
        )

        await asyncio.sleep(5)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👉 Задать вопрос",
                        callback_data="open_ai_chat",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="👉 Узнать больше",
                        callback_data="menu_learn_more",
                    )
                ],
            ]
        )

        await bot.send_message(
            callback.message.chat.id,
            (
                "Если результат отозвался, "
                "предлагаю заглянуть немного глубже. 🔍\n\n"
                "Выбери удобный шаг ниже:"
            ),
            reply_markup=kb,
            parse_mode="HTML",
        )
