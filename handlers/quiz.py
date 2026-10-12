import asyncio
import logging

from aiogram import Dispatcher, Bot, types, F
from aiogram.fsm.context import FSMContext
from services.conversation_admission import is_private_coaching_chat
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
    persist_completed_quiz_result=None,
):

    async def reject(callback, reason):
        logging.info("quiz_callback_rejected reason=%s", reason)
        await callback.answer("Эта кнопка больше не активна.", show_alert=True)

    def matches_message(expected_id, message):
        return (
            type(expected_id) is int
            and expected_id > 0
            and expected_id == message.message_id
        )

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
        if not is_private_coaching_chat(callback.message.chat, callback.from_user.id):
            await callback.answer()
            return
        data = await state.get_data()
        if await state.get_state() is not None:
            await reject(callback, "wrong_state")
            return
        if not matches_message(data.get("welcome_message_id"), callback.message):
            await reject(callback, "stale_message")
            return
        await callback.answer()

        try:
            await callback.message.delete()
        except Exception:
            logging.exception("Failed to delete welcome message")

        name = get_user_first_name(callback.from_user)

        await state.update_data(
            welcome_message_id=None,
            last_question_message_id=None,
            result_processing_message_id=None,
            quiz_entry_message_id=None,
            archetype=None,
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
        if not is_private_coaching_chat(callback.message.chat, callback.from_user.id):
            await callback.answer()
            return
        if await state.get_state() != state_cls.QUESTION_STEP.state:
            await reject(callback, "wrong_state")
            return
        data = await state.get_data()
        if not matches_message(data.get("last_question_message_id"), callback.message):
            await reject(callback, "stale_message")
            return
        questions = data.get("quiz_questions")
        idx = data.get("current_q_idx")
        answers = data.get("answers_list")
        current_score = data.get("total_score")
        if (
            not isinstance(questions, list)
            or questions != default_questions
            or type(idx) is not int
            or not 0 <= idx < len(questions)
            or not isinstance(answers, list)
            or len(answers) != idx
            or type(current_score) is not int
        ):
            await reject(callback, "wrong_state")
            return
        parts = callback.data.split("_")
        if len(parts) != 3 or parts[:2] != ["q", "ans"] or not parts[2].isdigit():
            await reject(callback, "invalid_value")
            return
        option_index = int(parts[2])
        options = questions[idx]["options"]
        if not 0 <= option_index < len(options):
            await reject(callback, "invalid_value")
            return
        await callback.answer()

        try:
            await bot.send_chat_action(callback.message.chat.id, "typing")
        except Exception:
            pass
        await asyncio.sleep(2)

        # /start or another accepted answer may have changed the volatile step
        # while the acknowledgement delay was in progress.
        fresh = await state.get_data()
        if (
            await state.get_state() != state_cls.QUESTION_STEP.state
            or fresh.get("last_question_message_id") != callback.message.message_id
            or fresh.get("current_q_idx") != idx
        ):
            logging.info("quiz_callback_rejected reason=duplicate")
            return

        option = options[option_index]
        updated_answers = list(answers)
        updated_answers.append({
            "q": idx + 1,
            "choice": option["text"],
            "score": option["score"],
        })
        await state.update_data(
            total_score=current_score + option["score"],
            current_q_idx=idx + 1,
            answers_list=updated_answers,
            last_question_message_id=None,
        )
        await render_question_step(
            callback.message,
            state,
            delete_previous=True,
        )

    @dp.callback_query(F.data == "show_result")
    async def show_result(
        callback: types.CallbackQuery,
        state: FSMContext,
    ):
        if not is_private_coaching_chat(callback.message.chat, callback.from_user.id):
            await callback.answer()
            return
        if await state.get_state() != state_cls.CALC.state:
            await reject(callback, "wrong_state")
            return
        data = await state.get_data()
        if not matches_message(data.get("last_question_message_id"), callback.message):
            await reject(callback, "stale_message")
            return
        total = data.get("total_score", 0)
        questions = data.get("quiz_questions")
        answers = data.get("answers_list")
        completed = (
            isinstance(questions, list)
            and questions == default_questions
            and bool(questions)
            and isinstance(answers, list)
            and len(answers) == len(questions)
            and data.get("current_q_idx") == len(questions)
            and type(total) is int
            and 0 <= total <= 6
        )
        if completed:
            for index, (question, answer) in enumerate(zip(questions, answers), 1):
                options = question.get("options") if isinstance(question, dict) else None
                if (
                    not isinstance(answer, dict)
                    or answer.get("q") != index
                    or not isinstance(options, list)
                    or not any(
                        answer.get("choice") == option.get("text")
                        and type(answer.get("score")) is int
                        and answer["score"] == option.get("score")
                        for option in options
                    )
                ):
                    completed = False
                    break
        if not completed or sum(answer["score"] for answer in answers) != total:
            await reject(callback, "invalid_value")
            return

        # Consume the completion button before delayed UI work.
        await state.update_data(
            last_question_message_id=None,
            result_processing_message_id=callback.message.message_id,
        )
        await callback.answer()

        try:
            await callback.message.delete()
        except Exception:
            pass

        try:
            await bot.send_chat_action(callback.message.chat.id, "upload_photo")
        except Exception:
            pass
        await asyncio.sleep(5)
        if (
            await state.get_state() != state_cls.CALC.state
            or (await state.get_data()).get("result_processing_message_id")
            != callback.message.message_id
        ):
            logging.info("quiz_callback_rejected reason=wrong_state")
            return

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

        # Durable result precedes both the FSM cache and result/entry UI.
        # A failed write cannot leave a newly shown result with no DB proof.
        if persist_completed_quiz_result is not None:
            await persist_completed_quiz_result(callback.from_user.id, archetype)
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

        entry_menu = await bot.send_message(
            callback.message.chat.id,
            (
                "Если результат отозвался, "
                "предлагаю заглянуть немного глубже. 🔍\n\n"
                "Выбери удобный шаг ниже:"
            ),
            reply_markup=kb,
            parse_mode="HTML",
        )
        await state.update_data(
            quiz_entry_message_id=entry_menu.message_id,
            result_processing_message_id=None,
        )
