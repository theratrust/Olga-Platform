import json
import os


BASE_PATH = "/app/knowledge/method"

METHOD_CORE_FILES = [
    "метод_Ольги.md",
    "принципы.md",
    "границы.md",
    "паттерны.md",
    "язык_и_стиль.md",
]


def load_shadow_light_version(version: str):
    path = os.path.join(
        BASE_PATH,
        "shadow_light",
        version,
    )

    with open(
        os.path.join(path, "questions.json"),
        "r",
        encoding="utf-8",
    ) as f:
        questions = json.load(f)

    with open(
        os.path.join(path, "metadata.json"),
        "r",
        encoding="utf-8",
    ) as f:
        metadata = json.load(f)

    return {
        "metadata": metadata,
        "questions": questions,
    }


def load_method_core() -> str:
    sections = []

    for filename in METHOD_CORE_FILES:
        path = os.path.join(BASE_PATH, filename)

        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Method core file is missing: {path}"
            )

        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            raise ValueError(
                f"Method core file is empty: {path}"
            )

        sections.append(
            f"===== {filename} =====\n{content}"
        )

    return "\n\n".join(sections)
