import logging

from prompts.admin import ADMIN_SYSTEM_PROMPT

from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext

from utils.telegram import send_long_message

def register_voice(
    dp: Dispatcher,
    bot: Bot,
    ai_client,
    model_name: str,
    admin_ids: list[int],
    transcribe_audio_file,
    ai_chat_handler,
):

    @dp.message(F.voice | F.audio)
    async def handle_voice_note(
        message: types.Message,
        state: FSMContext,
    ):
        user_id = message.from_user.id

        voice_obj = message.voice or message.audio
        file_info = await bot.get_file(voice_obj.file_id)
        file_bytes_io = await bot.download_file(file_info.file_path)
        file_bytes = file_bytes_io.read()

        await bot.send_chat_action(message.chat.id, "typing")

        transcribed_text = await transcribe_audio_file(file_bytes)

        if not transcribed_text:
            await message.answer(
                "❌ Не удалось распознать голосовое сообщение."
            )
            return

        if user_id in admin_ids:
            try:
                response = await ai_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": ADMIN_SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": transcribed_text,
                        },
                    ],
                    extra_headers={
                        "HTTP-Referer": "https://telegram.org",
                        "X-Title": "Olga Coaching Bot Admin",
                    },
                )

                answer = response.choices[0].message.content

                response_text = (
                    f"🎙️ Распознано:\n"
                    f"«{transcribed_text}»\n\n"
                    f"🤖 Ответ модели {model_name}:\n\n"
                    f"{answer}"
                )

                await send_long_message(message, response_text)

            except Exception as exc:
                logging.exception("Admin voice request failed")
                await message.answer(
                    f"❌ Ошибка обращения к модели: {exc}"
                )

            return

        message.text = transcribed_text
        await ai_chat_handler(message, state)
