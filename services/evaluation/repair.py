"""Shared deterministic format-repair policy; no gold labels or runtime routing."""

import copy
import re
from pathlib import PurePosixPath

from .model_adapter import sanitize


RETRY_INSTRUCTION = (
    "Предыдущий ответ не прошёл техническую проверку контракта.\n"
    "Исправь только формат и структуру.\n"
    "Верни только один полный JSON-объект по требуемому контракту.\n"
    "Не добавляй новые поля.\n"
    "Не используй Markdown-блоки.\n"
    "Не объясняй ответ вне JSON."
)
CONTRACT_RETRY_KINDS = frozenset({
    "schema_shape_error", "invalid_source_heading", "source_reference_inclusion_error",
    "null_score_without_context", "missing_required_field", "unknown_field",
})


def _safe_generated_paths(result):
    """Lexical gate only; actual containment remains the canonical validator's job."""
    if not isinstance(result, dict):
        return False
    refs = list(result.get("source_refs", [])) if isinstance(result.get("source_refs"), list) else []
    violations = result.get("violations", [])
    if isinstance(violations, list):
        for violation in violations:
            if isinstance(violation, dict) and isinstance(violation.get("source_refs"), list):
                refs.extend(violation["source_refs"])
    paths = [ref.get("path") for ref in refs if isinstance(ref, dict)]
    return bool(paths) and all(isinstance(path, str) and "\x00" not in path and "\\" not in path
        and not PurePosixPath(path).is_absolute() and ".." not in PurePosixPath(path).parts
        and PurePosixPath(path).parts[:2] == ("knowledge", "method")
        and len(PurePosixPath(path).parts) > 2 for path in paths)


def contract_diagnostic(error, result, secret=None):
    """Classify deterministic validator messages; do not expose raw filesystem errors.

    Messages use fixed descriptions and trusted field locations. No supplied values,
    derived expected decisions, headers or filesystem exception text are forwarded.
    """
    message = str(error)
    match = re.match(r"^((?:result|hard_fail|decision|overall|reason|scores|source_refs|violations|insufficient_context)(?:\[\d+\]|\.[a-z_]+)*):", message)
    label = match.group(1) if match else "result"
    kind, description, repairable = "other_contract_error", "contract invariant failed", False
    if "heading does not exist" in message:
        kind, description = "invalid_source_heading", "heading not found; use the exact source heading"
    elif any(marker in message for marker in (".path:", "source path validation failed", "cannot read source", "method directory escapes")):
        kind, description = "invalid_source_path", "invalid or unavailable source path"
        unsafe = any(marker in message for marker in ("escapes", "embedded NUL", "cannot read source", "source path validation failed"))
        repairable = not unsafe and _safe_generated_paths(result) and any(marker in message for marker in (
            "must be canonical and under knowledge/method/", "source file does not exist"))
    elif "missing from top-level source_refs" in message:
        kind, description = "source_reference_inclusion_error", "violation source reference missing from top-level source_refs"
    elif message == "null scores require insufficient context":
        kind, description = "null_score_without_context", "null scores require insufficient_context.present=true with missing-context items"
    elif "by contract priority" in message:
        kind, description = "decision_priority_error", "declared label contradicts contract priority"
    elif "not an exact substring" in message:
        kind, description = "excerpt_evidence_error", "excerpt is not an exact substring of candidate_response"
    elif ": invalid fields (required:" in message:
        target = result
        try:
            for token in re.findall(r"[a-z_]+|\d+", label):
                if token != "result":
                    target = target[int(token)] if token.isdigit() else target[token]
            required = set(re.findall(r"'([a-z_]+)'", message.split("required:", 1)[1]))
            missing = required - set(target)
            kind = "missing_required_field" if missing else "unknown_field"
            description = "missing required fields: " + ", ".join(sorted(missing)) if missing else "unknown object fields are forbidden"
        except (KeyError, IndexError, TypeError):
            kind, description = "schema_shape_error", "object fields do not match the contract"
    elif ".rule_id: invalid value" in message or ".rule_ids: invalid value" in message:
        # Unknown HF IDs are not a format-only judgment repair.
        kind, description = "other_contract_error", "unknown HF rule identifier"
    elif any(marker in message for marker in (": expected object", ": expected nonempty string", ": expected array",
            ": must not be empty", ": expected boolean", ": invalid value", "scores: values must be integer")):
        kind, description = "schema_shape_error", "invalid contract field shape, type or allowed value"
    diagnostic = {"contract_error_kind": kind, "contract_error": sanitize(label + ": " + description, secret),
                  "structural_retry_eligible": kind in CONTRACT_RETRY_KINDS or kind == "invalid_source_path" and repairable}
    return diagnostic


def retry_messages(messages, error):
    """Original input plus safe technical error; no gold, prior output or reasoning."""
    instruction = RETRY_INSTRUCTION
    if error.get("contract_error"):
        instruction = "Предыдущий ответ не прошёл техническую проверку контракта.\n\nОшибка:\n" + error["contract_error"] + "\n\n" + RETRY_INSTRUCTION.split("\n", 1)[1]
    return copy.deepcopy(messages) + [{"role": "user", "content": instruction}]


def retry_eligible(attempt):
    error = attempt["error"]
    if error is None:
        return False
    return error["kind"] in {"truncated_response", "empty_response", "malformed_model_json"} or (
        error["kind"] == "contract_invalid_result" and error.get("structural_retry_eligible") is True)
