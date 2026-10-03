import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

from database import (
    init_db,
    get_post_names,
    get_channel_post,
)
from services.intent import IntentDetector
from services.ai_cms import rewrite_post

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "z-ai/glm-5.2")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


async def main():

    await init_db()

    posts = await get_post_names()

    print("\nKnown posts:")
    print(posts)
    print()

    detector = IntentDetector(client, MODEL_NAME)

    user_message = input("Instruction: ")

    result = await detector.detect(user_message, posts)

    print("\nDetected intent:")
    print(result)

    if result.get("intent") != "rewrite_post":
        return

    post_name = result.get("post")

    if not post_name:
        print("\nNo matching post.")
        return

    row = await get_channel_post(post_name)

    if row is None:
        print("\nPost not found in database.")
        return

    message_id, original_text = row

    print("\n----------------------------------------")
    print("ORIGINAL")
    print("----------------------------------------")
    print(original_text)

    rewritten = await rewrite_post(
        client,
        MODEL_NAME,
        original_text,
        result["instruction"],
    )

    print("\n----------------------------------------")
    print("REWRITTEN")
    print("----------------------------------------")
    print(rewritten)


if __name__ == "__main__":
    asyncio.run(main())
