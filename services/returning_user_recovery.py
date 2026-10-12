"""Volatile coaching-state restoration from explicit durable eligibility."""

import logging

from services.conversation_admission import private_message_marker


async def ensure_coaching_state(
    message,
    state,
    state_cls,
    get_coaching_resume_conversation_id,
    *,
    mode: str,
) -> bool:
    """Restore only a private, fresh empty FSM; never mutate durable state.

    Callers coordinate this check with their existing per-user admission lock.
    A missing marker/session or an in-progress onboarding FSM fails closed.
    """
    if private_message_marker(message) is None:
        return False
    current_state = await state.get_state()
    if current_state == state_cls.AI_CHAT.state:
        return True
    home_state = getattr(getattr(state_cls, "HOME", None), "state", None)
    data = await state.get_data()
    at_current_home = (
        home_state is not None
        and current_state == home_state
        and type(data.get("home_message_id")) is int
        and data["home_message_id"] > 0
    )
    if (
        get_coaching_resume_conversation_id is None
        or (not at_current_home and (current_state is not None or data))
    ):
        return False
    conversation_id = await get_coaching_resume_conversation_id(message.from_user.id)
    if conversation_id is None:
        return False
    await state.set_state(state_cls.AI_CHAT)
    await state.update_data(home_message_id=None, shadow_conversation_id=conversation_id)
    logging.info(
        "returning_user_state_restored source=durable_eligibility mode=%s conversation_id=%s",
        mode,
        conversation_id,
    )
    return True
