import os
import asyncio
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from openai import AsyncOpenAI

from database import (
    init_db, add_chat_message, get_recent_history,
    create_pending_draft, get_pending_draft, update_draft_status,
    clear_chat_history,
)

from handlers.start import register_start
from handlers.callbacks import register_callbacks
from handlers.quiz import register_quiz
from handlers.admin import register_admin
from handlers.chat import register_chat
from handlers.voice import register_voice
from handlers.knowledge import register_knowledge
from services.transcription import transcribe_audio_file as transcribe_audio
from handlers.knowledge_view import register_knowledge_view
from handlers.method_drafts import register_method_drafts
from handlers.method_assets import register_method_assets
from services.methods.loader import load_shadow_light_version
from services.evaluation.runtime import ShadowDispatcher
from services.quality_evaluation.runtime import QualityShadowDispatcher

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "z-ai/glm-5.2")

DEV_DIRECT_CHAT = os.getenv(
    "DEV_DIRECT_CHAT",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", os.getenv("OLGA_ADMIN_ID", "5158427705"))
ADMIN_IDS = [int(aid.strip()) for aid in ADMIN_IDS_RAW.split(",") if aid.strip().isdigit()]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ai_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class Quiz(StatesGroup):
    QUESTION_STEP = State()
    CALC = State()
    AI_CHAT = State()

class OlgaApproval(StatesGroup):
    WAITING_FOR_EDIT = State()

class OlgaKnowledge(StatesGroup):
    WAITING_FOR_CONTENT = State()

ACTIVE_METHOD_VERSION = "v1.1"

ACTIVE_METHOD = load_shadow_light_version(
    ACTIVE_METHOD_VERSION
)

DEFAULT_QUESTIONS = ACTIVE_METHOD["questions"]


def get_user_display_name(user: types.User) -> str:
    first = user.first_name or ""
    last = user.last_name or ""
    full = f"{first} {last}".strip()
    return full if full else f"User {user.id}"

def get_user_first_name(user: types.User) -> str:
    return user.first_name.strip() if user.first_name else "Гостья"

def get_image_file(filename: str) -> FSInputFile:
    for p in [
        os.path.join(BASE_DIR, "images", filename),
        os.path.join("/opt/olga-coaching-bot/images", filename),
        os.path.join("/app", "images", filename),
        filename
    ]:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return FSInputFile(p)
    return FSInputFile(os.path.join(BASE_DIR, "images", "q1_welcome.jpg"))

register_start(
    dp,
    get_user_first_name,
    get_image_file,
)

register_callbacks(
    dp,
    bot,
    Quiz,
)

register_quiz(
    dp=dp,
    bot=bot,
    state_cls=Quiz,
    default_questions=DEFAULT_QUESTIONS,
    get_user_first_name=get_user_first_name,
    get_image_file=get_image_file,
)

register_admin(
    dp=dp,
    bot=bot,
    ai_client=ai_client,
    model_name=MODEL_NAME,
    admin_ids=ADMIN_IDS,
    approval_state=OlgaApproval,
    get_pending_draft=get_pending_draft,
    update_draft_status=update_draft_status,
    add_chat_message=add_chat_message,
)


register_knowledge(
    dp=dp,
    admin_ids=ADMIN_IDS,
    state_cls=OlgaKnowledge,
)

register_knowledge_view(
    dp=dp,
    admin_ids=ADMIN_IDS,
    ai_client=ai_client,
    model_name=MODEL_NAME,
)


register_method_drafts(
    dp=dp,
    admin_ids=ADMIN_IDS,
)


register_method_assets(
    dp=dp,
    admin_ids=ADMIN_IDS,
)

shadow_dispatcher = ShadowDispatcher()
quality_shadow_dispatcher = QualityShadowDispatcher()

ai_chat_handler = register_chat(
    dp=dp,
    bot=bot,
    ai_client=ai_client,
    model_name=MODEL_NAME,
    admin_ids=ADMIN_IDS,
    state_cls=Quiz,
    get_user_display_name=get_user_display_name,
    get_user_first_name=get_user_first_name,
    add_chat_message=add_chat_message,
    get_recent_history=get_recent_history,
    create_pending_draft=create_pending_draft,
    clear_chat_history=clear_chat_history,
    direct_chat=DEV_DIRECT_CHAT,
    shadow_observer=shadow_dispatcher.submit,
    quality_shadow_observer=quality_shadow_dispatcher.submit,
)

register_voice(
    dp=dp,
    bot=bot,
    ai_client=ai_client,
    model_name=MODEL_NAME,
    admin_ids=ADMIN_IDS,
    transcribe_audio_file=lambda file_bytes: transcribe_audio(
    ai_client,
    file_bytes,
),
    ai_chat_handler=ai_chat_handler,
)

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        try:
            await shadow_dispatcher.close()
        finally:
            await quality_shadow_dispatcher.close()

if __name__ == "__main__":
    asyncio.run(main())
