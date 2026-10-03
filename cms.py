import os
import httpx
import logging

DIRECTUS_URL = os.getenv("DIRECTUS_URL", "http://directus:8055")
DIRECTUS_PUBLIC_URL = os.getenv("DIRECTUS_PUBLIC_URL", "").rstrip("/")

async def get_bot_settings():
    """Fetch system prompt, captions, and active image paths from Directus."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{DIRECTUS_URL}/items/bot_settings", timeout=3.0)
            if r.status_code == 200:
                data = r.json().get("data", {})
                
                def resolve_img_path(file_id, fallback):
                    if file_id and DIRECTUS_PUBLIC_URL:
                        return f"{DIRECTUS_PUBLIC_URL}/assets/{file_id}"
                    return fallback

                return {
                    "system_prompt": data.get("system_prompt"),
                    "start_caption": data.get("start_caption"),
                    "img_start": resolve_img_path(data.get("start_image"), "images/start.jpg"),
                    "img_svet": resolve_img_path(data.get("svet_image"), "images/svet.jpg"),
                    "img_poluten": resolve_img_path(data.get("poluten_image"), "images/poluten.jpg"),
                    "img_ten": resolve_img_path(data.get("ten_image"), "images/ten.jpg"),
                }
        except Exception as e:
            logging.warning(f"Could not fetch settings from Directus: {e}")
            
    return None

async def get_quiz_questions():
    """Fetch dynamic quiz questions sorted by question number."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{DIRECTUS_URL}/items/quiz_questions?sort=question_number", timeout=3.0)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    return data
        except Exception as e:
            logging.warning(f"Could not fetch quiz questions from Directus: {e}")
    return []

async def get_custom_buttons(location: str):
    """Fetch custom inline buttons assigned to a specific screen location."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{DIRECTUS_URL}/items/custom_buttons?filter[display_location][_eq]={location}&sort=sort_order",
                timeout=3.0
            )
            if r.status_code == 200:
                return r.json().get("data", [])
        except Exception as e:
            logging.warning(f"Could not fetch custom buttons from Directus: {e}")
    return []
