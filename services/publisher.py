import json
from aiogram import Bot
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)


def build_keyboard(keyboard_json: str):
    """
    Convert JSON stored in database into aiogram keyboard.
    """

    if not keyboard_json:
        return None

    rows = json.loads(keyboard_json)

    keyboard = []

    for row in rows:
        buttons = []

        for btn in row:
            buttons.append(
                InlineKeyboardButton(
                    text=btn["text"],
                    callback_data=btn["callback"],
                )
            )

        keyboard.append(buttons)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def publish_page(bot: Bot, page: dict):
    """
    Publish a page to Telegram.

    page = {
        chat_id,
        message_id,
        photo_file_id,
        caption,
        keyboard_json
    }
    """

    keyboard = build_keyboard(page["keyboard_json"])

    media = InputMediaPhoto(
        media=page["photo_file_id"],
        caption=page["caption"],
    )

    await bot.edit_message_media(
        chat_id=page["chat_id"],
        message_id=page["message_id"],
        media=media,
        reply_markup=keyboard,
    )
