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
    if (
        current_state is not None
        or await state.get_data()
        or get_coaching_resume_conversation_id is None
    ):
        return False
    conversation_id = await get_coaching_resume_conversation_id(message.from_user.id)
    if conversation_id is None:
        return False
    await state.set_state(state_cls.AI_CHAT)
    await state.update_data(shadow_conversation_id=conversation_id)
    logging.info(
        "returning_user_state_restored source=durable_eligibility mode=%s conversation_id=%s",
        mode,
        conversation_id,
    )
    return True
