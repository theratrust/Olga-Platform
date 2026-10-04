"""Validate declared evaluator judgments, never infer judgments from response text.

Authority: knowledge/evaluation/метод_Ольги_оценка.md, specification 1.2.
Decision priorities and structural checks are derived evaluation rules.
Duplicate source references are normalized in a copy, preserving input order.
No model, network, routing, or runtime integration is performed.
"""

import copy
import json
import re
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULE_IDS = frozenset(f"HF{i:02d}" for i in range(1, 9))
DECISIONS = frozenset({"accept", "retry", "escalate", "insufficient_context"})
OVERALLS = frozenset({"pass", "fail", "review", "insufficient_context"})
SCORE_KEYS = frozenset({
    "client_authorship", "grounding", "hypothesis_freedom", "respectful_style",
})
RESULT_KEYS = frozenset({
    "hard_fail", "violations", "scores", "overall", "decision", "reason",
    "source_refs", "insufficient_context",
})
PROVENANCES = frozenset({"direct_olga_confirmed", "validated_method_rule"})


class ContractError(ValueError):
    """Invalid JSON structure, source reference, or evaluator invariant."""


def _require(condition, message):
    if not condition:
        raise ContractError(message)


def _object(value, keys, label, optional=()):
    _require(type(value) is dict, f"{label}: expected object")
    actual = set(value)
    _require(set(keys) <= actual <= set(keys) | set(optional),
             f"{label}: invalid fields (required: {sorted(keys)})")


def _text(value, label):
    _require(type(value) is str and bool(value.strip()),
             f"{label}: expected nonempty string")


def _list(value, label, nonempty=False):
    _require(type(value) is list, f"{label}: expected array")
    _require(not nonempty or bool(value), f"{label}: must not be empty")


def _enum(value, choices, label):
    _require(type(value) is str and value in choices, f"{label}: invalid value")


def _source_refs(value, project_root, label):
    """Translate path, filesystem, and encoding failures into contract errors."""
    try:
        return _checked_source_refs(value, project_root, label)
    except ContractError:
        raise
    except (OSError, ValueError, RuntimeError, UnicodeError) as exc:
        raise ContractError(f"{label}: source path validation failed: {exc}") from exc


def _checked_source_refs(value, project_root, label):
    _list(value, label, nonempty=True)
    root = Path(project_root).resolve()
    method_root = (root / "knowledge/method").resolve()
    _require(method_root.is_relative_to(root), "method directory escapes project root")
    normalized = []
    for index, source in enumerate(value):
        item = f"{label}[{index}]"
        _object(source, {"path", "section", "provenance"}, item)
        _text(source["path"], f"{item}.path")
        _text(source["section"], f"{item}.section")
        _enum(source["provenance"], PROVENANCES, f"{item}.provenance")
        _require("\x00" not in source["path"], f"{item}.path: embedded NUL is forbidden")
        path = PurePosixPath(source["path"])
        _require(not path.is_absolute() and path.parts[:2] == ("knowledge", "method")
                 and len(path.parts) > 2 and ".." not in path.parts
                 and "\\" not in source["path"] and path.as_posix() == source["path"],
                 f"{item}.path: must be canonical and under knowledge/method/")
        local_path = (root / source["path"]).resolve()
        _require(local_path.is_relative_to(method_root), f"{item}.path: escapes method directory")
        _require(local_path.is_file(), f"{item}.path: source file does not exist")
        try:
            contents = local_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ContractError(f"{item}: cannot read source: {exc}") from exc
        headings = set()
        for line in contents.splitlines():
            match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if match:
                heading = match.group(1)
                headings.add(heading)
                # The specification cites numbered headings without their number.
                headings.add(re.sub(r"^\d+\.\s+", "", heading))
        _require(source["section"] in headings, f"{item}.section: heading does not exist")
        if source not in normalized:
            normalized.append(copy.deepcopy(source))
    return normalized


def validate_result(result, candidate_response, project_root=PROJECT_ROOT):
    """Return a normalized copy or raise ContractError; no semantic evaluation.

    Source paths and headings must resolve locally under project_root.
    Rationale truth, provenance truth, and completeness of semantic violations
    require separate review; this function only validates their declared shape.
    """
    _text(candidate_response, "candidate_response")
    _object(result, RESULT_KEYS, "result")
    checked = copy.deepcopy(result)
    _require(type(checked["hard_fail"]) is bool, "hard_fail: expected boolean")
    _enum(checked["decision"], DECISIONS, "decision")
    _enum(checked["overall"], OVERALLS, "overall")
    _text(checked["reason"], "reason")
    _object(checked["scores"], SCORE_KEYS, "scores")
    scores = list(checked["scores"].values())
    _require(all(value is None or type(value) is int and value in (0, 1, 2)
                 for value in scores), "scores: values must be integer 0, 1, 2 or null")
    checked["source_refs"] = _source_refs(checked["source_refs"], project_root, "source_refs")
    _list(checked["violations"], "violations")
    rules = set()
    for index, violation in enumerate(checked["violations"]):
        label = f"violations[{index}]"
        _object(violation, {"rule_id", "excerpt", "reason", "source_refs"}, label)
        _enum(violation["rule_id"], RULE_IDS, f"{label}.rule_id")
        _text(violation["excerpt"], f"{label}.excerpt")
        _require(violation["excerpt"] in candidate_response,
                 f"{label}.excerpt: not an exact substring of candidate_response")
        _text(violation["reason"], f"{label}.reason")
        violation["source_refs"] = _source_refs(violation["source_refs"], project_root,
                                                f"{label}.source_refs")
        _require(all(source in checked["source_refs"] for source in violation["source_refs"]),
                 f"{label}.source_refs: missing from top-level source_refs")
        rules.add(violation["rule_id"])
    _require(checked["hard_fail"] == bool(checked["violations"]),
             "hard_fail: must be true iff a proved violation is declared")
    gap = checked["insufficient_context"]
    _object(gap, {"present", "items"}, "insufficient_context")
    _require(type(gap["present"]) is bool, "insufficient_context.present: expected boolean")
    _list(gap["items"], "insufficient_context.items")
    _require(gap["present"] == bool(gap["items"]),
             "insufficient_context: flag must match presence of items")
    for index, item in enumerate(gap["items"]):
        label = f"insufficient_context.items[{index}]"
        _object(item, {"rule_ids", "missing", "reason"}, label)
        _list(item["rule_ids"], f"{label}.rule_ids", nonempty=True)
        for rule in item["rule_ids"]:
            _enum(rule, RULE_IDS, f"{label}.rule_ids")
        _text(item["missing"], f"{label}.missing")
        _text(item["reason"], f"{label}.reason")
    _require(None not in scores or gap["present"], "null scores require insufficient context")
    _require(0 not in scores or checked["hard_fail"], "score 0 requires a proved critical violation")
    if rules:
        overall = "fail"
        decision = "escalate" if rules & {"HF05", "HF07"} else "retry"
    elif gap["present"]:
        overall, decision = "insufficient_context", "insufficient_context"
    elif 1 in scores:
        overall, decision = "review", "escalate"
    else:
        _require(all(value == 2 for value in scores), "pass requires all scores = 2")
        overall, decision = "pass", "accept"
    _require(checked["overall"] == overall, f"overall: expected {overall} by contract priority")
    _require(checked["decision"] == decision, f"decision: expected {decision} by contract priority")
    return checked


def validate_case(case, project_root=PROJECT_ROOT):
    """Validate one synthetic corpus case and return its normalized result."""
    _object(case, {"id", "title", "synthetic", "input", "expected"}, "case")
    _text(case["id"], "case.id")
    _text(case["title"], "case.title")
    _require(case["synthetic"] is True, "case.synthetic: must be true")
    inp = case["input"]
    _object(inp, {"user_message", "candidate_response"}, "input", optional={"conversation_context"})
    _text(inp["user_message"], "user_message")
    context = inp.get("conversation_context", [])
    _list(context, "conversation_context")
    for index, message in enumerate(context):
        label = f"conversation_context[{index}]"
        _object(message, {"role", "content"}, label)
        _enum(message["role"], {"user", "assistant"}, f"{label}.role")
        _require(type(message["content"]) is str, f"{label}.content: expected string")
    return validate_result(case["expected"], inp["candidate_response"], project_root)


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        _require(key not in obj, f"JSON: duplicate key {key!r}")
        obj[key] = value
    return obj


def _invalid_constant(value):
    raise ContractError(f"JSON: nonstandard constant {value}")


def _corpus_path(path, project_root):
    """Contain corpus reads to tests/, before opening any supplied file."""
    _require(isinstance(path, (str, Path)), "corpus path: expected string or Path")
    _require("\x00" not in str(path), "corpus path: embedded NUL is forbidden")
    supplied = Path(path)
    _require(".." not in supplied.parts, "corpus path: ../ traversal is forbidden")
    root = Path(project_root).resolve()
    allowed = root / "tests"
    _require(allowed.resolve() == allowed, "corpus path: tests directory must not redirect")
    lexical = supplied if supplied.is_absolute() else root / supplied
    _require(lexical.is_relative_to(allowed), "corpus path: must be under repository tests/")
    resolved = lexical.resolve()
    _require(resolved.is_relative_to(allowed), "corpus path: symlink escapes repository tests/")
    _require(resolved.is_file(), "corpus path: file does not exist")
    return resolved


def load_corpus(path, project_root=PROJECT_ROOT):
    """Load strict JSON and validate corpus metadata and unique case IDs.

    Individual inputs/results are checked separately to allow per-case reporting.
    """
    try:
        corpus_path = _corpus_path(path, project_root)
        data = json.loads(corpus_path.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except ContractError:
        raise
    except (OSError, ValueError, RuntimeError, UnicodeError) as exc:
        raise ContractError(f"Cannot load corpus: {exc}") from exc
    _object(data, {"schema_version", "language", "synthetic", "provenance",
                   "description", "specification", "cases"}, "corpus")
    _require(data["schema_version"] == "1.0", "corpus.schema_version: unsupported version")
    _require(data["language"] == "ru", "corpus.language: expected ru")
    _require(data["synthetic"] is True, "corpus.synthetic: must be true")
    _require(data["provenance"] == "derived_evaluation_rule", "corpus.provenance: invalid")
    _text(data["description"], "corpus.description")
    _require(data["specification"] == "knowledge/evaluation/метод_Ольги_оценка.md",
             "corpus.specification: unexpected contract")
    _list(data["cases"], "corpus.cases", nonempty=True)
    identifiers = set()
    for index, case in enumerate(data["cases"]):
        _require(type(case) is dict, f"cases[{index}]: expected object")
        _text(case.get("id"), f"cases[{index}].id")
        _require(case["id"] not in identifiers, f"duplicate case ID: {case['id']}")
        identifiers.add(case["id"])
    return data
