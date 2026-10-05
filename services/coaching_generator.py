"""Shared coaching generation path; no delivery, persistence or evaluator policy."""
from prompts.coaching import build_coaching_prompt

DEFAULT_MAX_TOKENS = 350


def build_system_instruction(*, first_name, archetype):
    return build_coaching_prompt(first_name=first_name, archetype=archetype)


def build_messages(system_instruction, history):
    # Callers provide ordered history, already bounded exactly like chat's DB read.
    return [{"role": "system", "content": system_instruction}] + history


async def generate_candidate(ai_client, model_name, messages, *, max_tokens=DEFAULT_MAX_TOKENS):
    response = await ai_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        extra_headers={"HTTP-Referer": "https://telegram.org", "X-Title": "Olga Coaching Bot"},
    )
    return response.choices[0].message.content
