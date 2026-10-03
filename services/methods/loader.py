import json
import os


BASE_PATH = "/app/knowledge/method"


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
