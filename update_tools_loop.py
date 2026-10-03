import os

with open("bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# Make sure tools are imported and handled in ai_chat_handler / admin commands
print("Current bot.py lines:", len(content.splitlines()))
