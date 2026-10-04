"""Qualification orchestration, synthetic-only corpus selection and artifacts."""

import copy
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .contract import PROJECT_ROOT, ContractError, load_corpus, validate_case, validate_result
from .metrics import calculate_metrics, compare_results, qualification_outcome
from .model_adapter import AdapterError, ModelParseError, parse_model_json, sanitize


def select_cases(cases, case_ids=None, max_cases=None):
    if max_cases is not None and (type(max_cases) is not int or max_cases < 1):
        raise ValueError("max_cases must be a positive integer")
    ids = list(case_ids or [])
    if len(ids) != len(set(ids)) or set(ids) - {case["id"] for case in cases}:
        raise ValueError("Unknown or duplicate case ID")
    selected = [case for case in cases if not ids or case["id"] in ids]
    return selected[:max_cases] if max_cases is not None else selected


def load_labeled_cases(project_root=PROJECT_ROOT):
    root = Path(project_root)
    corpus = load_corpus(root / "tests/coaching_evaluator_cases.json", root)
    # No arbitrary user-supplied conversation or corpus path is accepted by the CLI.
    if len(corpus["cases"]) != 22:
        raise ContractError("Qualification requires the current 22-case synthetic corpus")
    for case in corpus["cases"]:
        validate_case(case, root)
    return corpus["cases"]


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


def _attempt(messages, adapter, candidate_response, expected, project_root, secret):
    record = {"raw_model_output": None, "raw_response": None, "response_metadata": None,
              "parsed_result": None, "validated_result": None, "contract_valid": False,
              "error": None, "comparison": None, "outcome": None}
    timer = time.perf_counter()
    try:
        reply = adapter.complete(messages, live=True)
        record["raw_model_output"] = sanitize(reply.text, secret)
        record["raw_response"] = sanitize(reply.raw_response, secret)
        record["response_metadata"] = sanitize(reply.details, secret)
        parsed = parse_model_json(reply.text)
        record["parsed_result"] = parsed
        actual = validate_result(parsed, candidate_response, project_root)
        record["validated_result"] = actual
        record["contract_valid"] = True
        record["comparison"] = compare_results(actual, expected)
    except AdapterError as exc:
        record["raw_response"] = exc.raw_response
        record["response_metadata"] = exc.details
        record["error"] = {"category": "adapter", "kind": exc.kind, "details": exc.details}
    except ModelParseError:
        record["error"] = {"category": "parse", "kind": "malformed_model_json"}
    except ContractError as exc:
        record["error"] = {"category": "contract", "kind": "contract_invalid_result",
                           **contract_diagnostic(exc, record["parsed_result"], secret)}
    record["outcome"] = qualification_outcome(record["contract_valid"], record["comparison"])
    record["latency_seconds"] = time.perf_counter() - timer
    return record


def retry_eligible(attempt):
    error = attempt["error"]
    if error is None:
        return False
    return error["kind"] in {"truncated_response", "empty_response", "malformed_model_json"} or (
        error["kind"] == "contract_invalid_result" and error.get("structural_retry_eligible") is True)


def qualify(cases, builder, adapter, config, *, live=False, project_root=PROJECT_ROOT,
            secret=None, retry_enabled=True):
    """One bounded structural retry; never retry a valid model judgment."""
    if live is not True:
        raise AdapterError("live_flag_required")
    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    records = []
    for case in cases:
        messages = builder.build(case["input"])
        expected = validate_case(case, project_root)
        first = _attempt(messages, adapter, case["input"]["candidate_response"], expected, project_root, secret)
        retry = None
        if retry_enabled and retry_eligible(first):
            retry = _attempt(retry_messages(messages, first["error"]), adapter,
                             case["input"]["candidate_response"], expected, project_root, secret)
        selected = retry if retry is not None else first
        record = copy.deepcopy(selected)
        record.update(case_id=case["id"], synthetic_input=copy.deepcopy(case["input"]),
                      expected_result=expected, attempt_count=2 if retry is not None else 1,
                      first_attempt=first, retry_attempt=retry,
                      final_selected_result=copy.deepcopy(selected["validated_result"]),
                      recovered=retry is not None and retry["contract_valid"],
                      latency_seconds=first["latency_seconds"] + (retry["latency_seconds"] if retry else 0))
        records.append(record)
    elapsed = time.perf_counter() - timer
    report = {"report_version": "1.5", "metadata": {
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model, "backend_host": urlsplit(config.base_url).hostname, "timeout_seconds": config.timeout,
        "temperature": 0, "max_tokens": config.max_tokens,
        "reasoning_config": config.reasoning, "reasoning_effort_config": config.reasoning_effort,
        "synthetic_only": True, "max_attempts": 2 if retry_enabled else 1,
        "case_ids": [case["id"] for case in cases],
        "specification_sha256": hashlib.sha256(builder.specification.encode("utf-8")).hexdigest(),
        "metrics_policy": "Agreements use all cases and final selected results; HF precision/recall use final valid responses only; zero denominators are null. First-pass reliability is reported separately. Full match includes rationales and list order after source-ref normalization."},
        "cases": records, "metrics": calculate_metrics(records, elapsed)}
    return sanitize(report, secret)


def model_slug(model):
    """Deterministic safe filename component; never a directory or shell command."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", model)[:64] or "model"


def write_report(report, *, secret=None, project_root=PROJECT_ROOT):
    """Write one exclusive, model-scoped JSON artifact, with credential redaction."""
    root = Path(project_root).resolve()
    destination = root / "artifacts/evaluation"
    if not destination.resolve().is_relative_to(root):
        raise ValueError("Artifact directory escapes repository")
    destination.mkdir(parents=True, exist_ok=True)
    if destination.resolve() != destination:
        raise ValueError("Artifact directory must not redirect")
    model = sanitize(report["metadata"]["model"], secret)
    slug = model_slug(model)
    digest = hashlib.sha256(model.encode("utf-8")).hexdigest()[:8]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = destination / f"{stamp}_{slug}_{digest}_{uuid.uuid4().hex[:8]}.json"
    encoded = json.dumps(sanitize(report, secret), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as artifact:
        artifact.write(encoded)
    return path
