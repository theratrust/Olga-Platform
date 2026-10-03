from openai import AsyncOpenAI


async def enrich_method_observation(
    ai_client,
    model_name,
    content: str,
):

    prompt = f"""
Ты — методолог, который помогает профессиональному коучу структурировать собственный метод.

Проанализируй наблюдение коуча.

Верни только JSON:

{{
  "type": "",
  "title": "",
  "principle": "",
  "questions": []
}}

Тип может быть:
- principle
- pattern
- question
- exercise
- observation

Наблюдение:

{content}
"""

    response = await ai_client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content
