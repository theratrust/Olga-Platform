"""Strict deterministic validation of declared quality labels; no semantic inference."""

import copy
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = "derived_product_quality_criteria"
SPECIFICATION = "knowledge/evaluation/качество_ответов_оценка.md"
DIMENSIONS = ("contextual_specificity", "progression", "non_repetition", "naturalness", "question_quality", "proportionality")
FLAG_DIMENSIONS = {
    "Q01_GENERIC_REFLECTION": "contextual_specificity", "Q02_UNNECESSARY_PARAPHRASE": "non_repetition",
    "Q03_REPETITIVE_STRUCTURE": "non_repetition", "Q04_LOW_PROGRESSION": "progression",
    "Q05_GENERIC_QUESTION": "question_quality", "Q06_TEMPLATE_LANGUAGE": "naturalness",
    "Q07_CONTEXT_MISS": "contextual_specificity", "Q08_OVERLONG_OR_UNDERDEVELOPED": "proportionality",
}
RESULT_KEYS = {"scores", "quality_flags", "overall_quality", "reason", "insufficient_context"}


class QualityContractError(ValueError):
    """Invalid shape or declared label consistency, never a methodology violation."""


def _require(condition, message):
    if not condition:
        raise QualityContractError(message)


def _object(value, keys, label, optional=()):
    _require(type(value) is dict, label + ": expected object")
    _require(set(keys) <= set(value) <= set(keys) | set(optional), label + ": missing or unknown fields")


def _text(value, label):
    _require(type(value) is str and bool(value.strip()), label + ": expected nonempty string")


def validate_input(value):
    _object(value, {"user_message", "candidate_response"}, "input", {"conversation_context", "recent_assistant_response_patterns"})
    _text(value["user_message"], "user_message")
    _text(value["candidate_response"], "candidate_response")
    context = value.get("conversation_context", [])
    _require(type(context) is list, "conversation_context: expected array")
    for message in context:
        _object(message, {"role", "content"}, "conversation_context message")
        _require(message["role"] in ("user", "assistant"), "context role: invalid")
        _require(type(message["content"]) is str, "context content: expected string")
    patterns = value.get("recent_assistant_response_patterns", [])
    _require(type(patterns) is list, "recent patterns: expected array")
    for pattern in patterns:
        _text(pattern, "recent pattern")
    return copy.deepcopy(value)


def validate_result(value, evaluator_input):
    """Return an independent copy. Quote anchoring does not prove flag truth."""
    inp = validate_input(evaluator_input)
    _object(value, RESULT_KEYS, "result")
    result = copy.deepcopy(value)
    _object(result["scores"], DIMENSIONS, "scores")
    for score in result["scores"].values():
        _require(score is None or type(score) is int and score in (0, 1, 2), "score must be 0, 1, 2 or null")
    _text(result["reason"], "reason")
    _require(result["overall_quality"] in ("strong", "acceptable", "weak", "insufficient_context"), "overall_quality: invalid")
    gap = result["insufficient_context"]
    _object(gap, {"present", "items"}, "insufficient_context")
    _require(type(gap["present"]) is bool, "context present: expected boolean")
    _require(type(gap["items"]) is list, "context items: expected array")
    _require(gap["present"] == bool(gap["items"]), "context flag/items mismatch")
    unknown = set()
    for item in gap["items"]:
        _object(item, {"dimensions", "missing", "reason"}, "context item")
        _require(type(item["dimensions"]) is list and bool(item["dimensions"]), "context dimensions: nonempty array required")
        _require(all(type(dim) is str and dim in DIMENSIONS for dim in item["dimensions"]), "unknown context dimension")
        _require(len(item["dimensions"]) == len(set(item["dimensions"])), "duplicate context dimension")
        unknown.update(item["dimensions"])
        _text(item["missing"], "missing context")
        _text(item["reason"], "context reason")
    null_dimensions = {dim for dim, score in result["scores"].items() if score is None}
    _require(null_dimensions == unknown and gap["present"] == bool(null_dimensions), "null scores must exactly match declared missing-context dimensions")
    flags = result["quality_flags"]
    _require(type(flags) is list, "quality_flags: expected array")
    texts = [inp["user_message"], inp["candidate_response"]] + [message["content"] for message in inp.get("conversation_context", [])]
    seen = set()
    for flag in flags:
        _object(flag, {"flag_id", "evidence"}, "quality flag")
        flag_id = flag["flag_id"]
        _require(type(flag_id) is str and flag_id in FLAG_DIMENSIONS, "unknown quality flag; HF IDs are not quality flags")
        _require(flag_id not in seen, "duplicate quality flag")
        seen.add(flag_id)
        _text(flag["evidence"], "flag evidence")
        _require(any(flag["evidence"] in text for text in texts), "evidence must be an exact substring of supplied conversation or candidate")
        _require(result["scores"][FLAG_DIMENSIONS[flag_id]] in (0, 1), "flag requires a concrete weakness in its corresponding dimension")
    scores = list(result["scores"].values())
    overall = "weak" if 0 in scores else "insufficient_context" if null_dimensions else "acceptable" if 1 in scores else "strong"
    _require(result["overall_quality"] == overall, "overall_quality contradicts scores/context priority")
    return result


def validate_case(case):
    _object(case, {"id", "title", "synthetic", "provenance", "input", "expected"}, "case")
    _require(type(case["id"]) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", case["id"]) is not None, "case ID: invalid")
    _text(case["title"], "title")
    _require(case["synthetic"] is True and case["provenance"] == PROVENANCE, "case provenance: derived synthetic product criteria required")
    return validate_result(case["expected"], case["input"])


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _invalid(value):
    raise QualityContractError("nonstandard JSON constant")


def load_corpus(path=None, project_root=PROJECT_ROOT):
    """Strict independent corpus envelope, contained under the repository tests/."""
    try:
        root = Path(project_root).resolve()
        allowed = root / "tests"
        _require(allowed.resolve() == allowed, "tests directory redirects")
        supplied = Path(path) if path is not None else Path("tests/response_quality_evaluator_cases.json")
        _require(".." not in supplied.parts and "\x00" not in str(supplied), "unsafe corpus path")
        local = supplied if supplied.is_absolute() else root / supplied
        _require(local.is_relative_to(allowed) and local.resolve().is_relative_to(allowed), "corpus must remain under tests/")
        corpus = json.loads(local.read_text(encoding="utf-8"), object_pairs_hook=_unique, parse_constant=_invalid)
    except QualityContractError:
        raise
    except (OSError, ValueError, RuntimeError, TypeError, UnicodeError) as exc:
        raise QualityContractError("cannot read quality corpus") from exc
    _object(corpus, {"schema_version", "language", "synthetic", "provenance", "specification", "description", "cases"}, "corpus")
    _require(type(corpus["schema_version"]) is str and corpus["schema_version"] == "1.0", "unsupported quality schema version")
    _require(corpus["language"] == "ru" and corpus["synthetic"] is True and corpus["provenance"] == PROVENANCE, "invalid corpus provenance/language")
    _require(corpus["specification"] == SPECIFICATION, "incorrect quality specification")
    _text(corpus["description"], "description")
    _require(type(corpus["cases"]) is list and bool(corpus["cases"]), "nonempty cases required")
    identifiers = set()
    for case in corpus["cases"]:
        validate_case(case)
        _require(case["id"] not in identifiers, "duplicate case ID")
        identifiers.add(case["id"])
    return corpus
