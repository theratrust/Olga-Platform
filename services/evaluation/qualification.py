"""Qualification orchestration, synthetic-only corpus selection and artifacts."""

import copy
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
    "Предыдущий ответ не прошёл техническую проверку формата.\n"
    "Верни только один полный JSON-объект по требуемому контракту.\n"
    "Не добавляй новые поля.\n"
    "Не используй Markdown-блоки.\n"
    "Не объясняй ответ вне JSON."
)


def structural_error_description(error):
    """Conservative allowlist; never forward raw validator text or priority labels."""
    message = str(error)
    policies = (
        (": expected object", "Ожидается JSON-объект."),
        (": invalid fields (required:", "Нарушен набор обязательных или разрешённых полей."),
        (": expected nonempty string", "Ожидается непустая строка."),
        (": expected array", "Ожидается массив."),
        (": must not be empty", "Обязательный массив не должен быть пустым."),
        (": expected boolean", "Ожидается логическое значение."),
        (": invalid value", "Значение не входит в разрешённое перечисление."),
        ("scores: values must be integer 0, 1, 2 or null", "Оценки должны быть целыми 0, 1, 2 или null."),
    )
    for marker, description in policies:
        if marker in message and "source path validation failed" not in message and "cannot read source" not in message:
            return description
    return None


def retry_messages(messages, error):
    """Original input plus trusted format repair instruction; no gold or reasoning."""
    instruction = RETRY_INSTRUCTION
    if error.get("structural_error"):
        instruction += "\nТехническая ошибка: " + error["structural_error"]
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
                           "structural_error": structural_error_description(exc)}
    record["outcome"] = qualification_outcome(record["contract_valid"], record["comparison"])
    record["latency_seconds"] = time.perf_counter() - timer
    return record


def retry_eligible(attempt):
    error = attempt["error"]
    if error is None:
        return False
    return error["kind"] in {"truncated_response", "empty_response", "malformed_model_json"} or (
        error["kind"] == "contract_invalid_result" and error.get("structural_error") is not None)


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
    report = {"report_version": "1.3", "metadata": {
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
