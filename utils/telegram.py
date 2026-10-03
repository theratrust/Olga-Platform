from aiogram import types


TELEGRAM_MESSAGE_LIMIT = 4000


def split_long_text(
    text: str,
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text.strip()

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n\n", 0, limit)

        if split_at == -1:
            split_at = remaining.rfind("\n", 0, limit)

        if split_at == -1:
            split_at = remaining.rfind(" ", 0, limit)

        if split_at == -1:
            split_at = limit

        chunk = remaining[:split_at].strip()

        if not chunk:
            chunk = remaining[:limit]
            split_at = limit

        chunks.append(chunk)
        remaining = remaining[split_at:].strip()

    return chunks


async def send_long_message(
    message: types.Message,
    text: str,
) -> None:
    for chunk in split_long_text(text):
        await message.answer(chunk)
