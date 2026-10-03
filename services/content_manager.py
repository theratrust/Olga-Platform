from openai import AsyncOpenAI


class ContentManager:

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model

    async def rewrite(self, current_text: str, instruction: str):

        prompt = f"""
You are Olga's Content Manager.

Rewrite the following Telegram channel post.

Requirements:
- Preserve meaning unless instructed otherwise.
- Keep formatting clean.
- Telegram compatible.
- Return ONLY the rewritten post.

Current post:

{current_text}

Instruction:

{instruction}
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.8,
        )

        return response.choices[0].message.content.strip()
