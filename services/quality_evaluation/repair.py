"""Allowlisted structural diagnostics; never expose result or gold values."""
import copy


def contract_diagnostic(error):
    message = str(error)
    repairable = False
    kind, description = "unrecoverable_contract_error", "Нарушено содержательное ограничение контракта."
    if "missing or unknown fields" in message:
        kind, description, repairable = "object_fields_error", "Набор полей объекта не соответствует схеме: отсутствуют обязательные или присутствуют лишние поля.", True
    elif message == "null scores must exactly match declared missing-context dimensions" or message == "context flag/items mismatch":
        kind, description, repairable = "context_consistency_error", "Структура объявления недостающего контекста не согласована с null и списком измерений.", True
    elif any(part in message for part in ("expected object", "expected array", "expected nonempty string", "expected boolean", "nonempty array required", "duplicate context dimension", "duplicate quality flag")):
        kind, description, repairable = "schema_shape_error", "Тип или структура поля не соответствует схеме.", True
    # Invalid labels, score range, flag IDs, evidence and score/flag/overall
    # contradictions are deliberately excluded: repairs could change judgment.
    return {"contract_error_kind": kind, "contract_error": description,
            "structural_retry_eligible": repairable}


def retry_eligible(attempt):
    error = attempt["error"]
    return bool(error and (error["kind"] in {"empty_response", "truncated_response", "malformed_json"}
                or error.get("structural_retry_eligible") is True))


def retry_messages(messages, error):
    diagnostics = {
        "empty_response": "Получен пустой ответ.",
        "truncated_response": "Ответ был обрезан провайдером.",
        "malformed_json": "Ответ не является одним корректным JSON-объектом.",
    }
    # Reconstruct from allowlisted kinds; even a supplied diagnostic cannot leak.
    if error["kind"] == "contract_invalid_output":
        descriptions = {
            "object_fields_error": "Набор полей объекта не соответствует схеме.",
            "context_consistency_error": "Объявление недостающего контекста не согласовано с null и списком измерений.",
            "schema_shape_error": "Тип или структура поля не соответствует схеме.",
        }
        description = descriptions[error["contract_error_kind"]]
    else:
        description = diagnostics[error["kind"]]
    instruction = ("Предыдущий ответ не прошёл техническую проверку. Ошибка: " + description +
                   " Исправь только формат и структуру. Верни один полный JSON-объект по контракту, без лишних полей, Markdown и текста вне JSON.")
    return copy.deepcopy(messages) + [{"role": "user", "content": instruction}]
