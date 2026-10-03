import json


def parse_method_ai_response(text: str):

    try:
        data = json.loads(text)

        return {
            "type": data.get("type", "observation"),
            "title": data.get("title", ""),
            "principle": data.get("principle", ""),
            "questions": data.get("questions", []),
        }

    except Exception:

        return {
            "type": "observation",
            "title": "AI draft",
            "principle": text,
            "questions": [],
        }
