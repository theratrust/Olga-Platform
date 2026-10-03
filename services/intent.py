import json


class IntentDetector:

    def __init__(self, client, model):
        self.client = client
        self.model = model

    async def detect(self, user_text: str, posts: list[str]):

        post_list = "\n".join(f"- {p}" for p in posts)

        prompt = f"""
You are the intent detection engine for a Telegram CMS.

Return ONLY valid JSON.

Possible intents:

rewrite_post
publish_post
cancel
unknown

Existing channel posts:

{post_list}

Rules:

- If the user wants to modify an existing channel post,
  intent = rewrite_post.

- If the user refers to one of the existing posts,
  return its exact name.

- If no post can be identified,
  post=null.

Examples:

User:
Rewrite the welcome message and make it warmer.

JSON:
{{
    "intent":"rewrite_post",
    "post":"welcome",
    "instruction":"make it warmer"
}}

User:
Сделай приветствие более дружелюбным.

JSON:
{{
    "intent":"rewrite_post",
    "post":"welcome",
    "instruction":"сделай более дружелюбным"
}}

User:
Publish it.

JSON:
{{
    "intent":"publish_post"
}}

User:
Cancel.

JSON:
{{
    "intent":"cancel"
}}

Now analyse:

{user_text}
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        text = response.choices[0].message.content.strip()

        try:
            return json.loads(text)
        except Exception:
            return {
                "intent": "unknown",
                "raw": text
            }
