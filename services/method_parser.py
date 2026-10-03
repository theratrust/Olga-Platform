import json


def _extract_json_payload(text: str) -> str:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    return cleaned


def parse_method_ai_response(text: str):
    try:
        payload = _extract_json_payload(text)
        data = json.loads(payload)

        questions = data.get("questions", [])

        if not isinstance(questions, list):
            questions = []

        return {
            "type": data.get("type", "observation"),
            "title": data.get("title", ""),
            "principle": data.get("principle", ""),
            "questions": questions,
        }

    except Exception:
        return {
            "type": "observation",
            "title": "AI draft",
            "principle": text,
            "questions": [],
        }
