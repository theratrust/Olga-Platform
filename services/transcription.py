import io
import logging


async def transcribe_audio_file(
    ai_client,
    file_bytes: bytes,
    filename: str = "voice.ogg",
) -> str:
    audio_file = io.BytesIO(file_bytes)
    audio_file.name = filename

    try:
        transcript = await ai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        return transcript.text

    except Exception as exc:
        logging.error(
            "Whisper transcription error: %s",
            exc,
        )
        return ""
