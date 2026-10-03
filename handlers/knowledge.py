import logging

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from services.knowledge import create_knowledge_proposal


def register_knowledge(
    dp: Dispatcher,
    admin_ids: list[int],
    state_cls,
):

    @dp.message(F.text == "/метод")
    async def start_knowledge_capture(
        message: types.Message,
        state: FSMContext,
    ):
        if message.from_user.id not in admin_ids:
            return

        await state.set_state(
            state_cls.WAITING_FOR_CONTENT
        )

        await message.answer(
    "Пришли идею или наблюдение, которое нужно добавить в твой метод.\n\n"
    "Это может быть:\n"
    "- принцип, который ты используешь в работе\n"
    "- наблюдение из практики с клиентами\n"
    "- идея для работы с женщинами после переезда\n"
    "- повторяющийся паттерн, который ты замечаешь\n"
    "- вопрос, который помогает клиенткам раскрыться"
)


    @dp.message(StateFilter(state_cls.WAITING_FOR_CONTENT), F.text & ~F.text.startswith("/"))
    async def save_knowledge_content(
        message: types.Message,
        state: FSMContext,
    ):
        logging.info(
            f"Knowledge content received from {message.from_user.id}"
        )

        if message.from_user.id not in admin_ids:
            return

        proposal_id = await create_knowledge_proposal(
            source_type="telegram",
            source_name="Olga Telegram",
            category="UNCLASSIFIED",
            title="New knowledge input",
            content=message.text,
            knowledge_type="observation",
        )

        await state.clear()

        logging.info(
            f"Knowledge proposal created: {proposal_id}"
        )

        await message.answer(
            f"✅ Материал сохранён.\n\n"
            f"Идея сохранена в черновиках твоего метода.\n\n"
            f"Запись №{proposal_id} ждёт твоего подтверждения."
        )
