import re

with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# Add tools import if not present
if "from tools import" not in code:
    code = "from tools import modify_bot_code, run_shell_command\nimport json\n" + code

# Write back patched file
with open("bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Bot code successfully patched with tool integrations.")
