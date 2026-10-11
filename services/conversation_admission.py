"""Private coaching admission metadata and short, process-local user locks."""

import asyncio
from weakref import WeakValueDictionary


_locks = WeakValueDictionary()


def admission_lock(user_id: int) -> asyncio.Lock:
    """The DB cutoff, not this process-local lock, fences stale messages."""
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def is_private_coaching_chat(chat, user_id: int) -> bool:
    return (
        chat is not None
        and getattr(chat, "type", None) == "private"
        and getattr(chat, "id", None) == user_id
    )


def private_message_marker(message):
    user = getattr(message, "from_user", None)
    user_id = getattr(user, "id", None)
    if not is_private_coaching_chat(getattr(message, "chat", None), user_id):
        return None
    message_id = getattr(message, "message_id", None)
    if type(message_id) is not int or message_id <= 0:
        return None
    return (message.chat.id, message_id)
