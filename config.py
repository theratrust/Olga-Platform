import os
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------

ENV_FILE = os.getenv("ENV_FILE", ".env.dev")

load_dotenv(ENV_FILE)

# ---------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
]

OLGA_ADMIN_ID = int(
    os.getenv(
        "OLGA_ADMIN_ID",
        ADMIN_IDS[0] if ADMIN_IDS else "0"
    )
)

# ---------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "z-ai/glm-5.2"
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

DB_NAME = os.getenv(
    "DB_NAME",
    "dev_bot.db"
)

# ---------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------

IMAGE_DIR = "images"

# ---------------------------------------------------------------------
# Telegram CMS
# ---------------------------------------------------------------------

PAGE_WELCOME = "welcome"
PAGE_ABOUT = "about"
PAGE_CONTACT = "contact"
PAGE_ARTICLES = "articles"

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO"
)
