#!/bin/bash
set -e

FILE="bot.py"

echo "Creating backup..."
cp "$FILE" "${FILE}.before-method-loader"

echo "Adding method loader import..."

python3 - <<'PY'
from pathlib import Path

p = Path("bot.py")
text = p.read_text(encoding="utf-8")

if "from services.methods.loader import load_shadow_light_version" not in text:
    anchor = "from "
    lines = text.splitlines()

    # add after last import line
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            insert_at = i + 1

    lines.insert(
        insert_at,
        "from services.methods.loader import load_shadow_light_version"
    )

    text = "\n".join(lines) + "\n"

p.write_text(text, encoding="utf-8")
PY

echo "Replacing DEFAULT_QUESTIONS with loader version..."

python3 - <<'PY'
from pathlib import Path
import re

p = Path("bot.py")
text = p.read_text(encoding="utf-8")

pattern = r"DEFAULT_QUESTIONS = \[.*?\n\]\n"

replacement = """ACTIVE_METHOD_VERSION = \"v1.0\"

ACTIVE_METHOD = load_shadow_light_version(
    ACTIVE_METHOD_VERSION
)

DEFAULT_QUESTIONS = ACTIVE_METHOD[\"questions\"]

"""

new_text, count = re.subn(
    pattern,
    replacement,
    text,
    flags=re.S
)

if count != 1:
    raise SystemExit(
        f"Expected 1 DEFAULT_QUESTIONS block, found {count}"
    )

p.write_text(new_text, encoding="utf-8")

print("Replacement complete")
PY

echo "Showing relevant lines:"
grep -n -A12 "ACTIVE_METHOD" bot.py

echo "Done."
