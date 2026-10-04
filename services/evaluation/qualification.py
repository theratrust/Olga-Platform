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


def qualify(cases, builder, adapter, config, *, live=False, project_root=PROJECT_ROOT, secret=None):
    """Infrastructure failures are records; semantic mismatches never abort a run."""
    if live is not True:
        raise AdapterError("live_flag_required")
    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    records = []
    for case in cases:
        messages = builder.build(case["input"])
        expected = validate_case(case, project_root)
        record = {"case_id": case["id"], "synthetic_input": copy.deepcopy(case["input"]),
                  "raw_model_output": None, "raw_response": None, "response_metadata": None, "parsed_result": None,
                  "validated_result": None, "expected_result": expected,
                  "contract_valid": False, "error": None, "comparison": None, "outcome": None}
        case_timer = time.perf_counter()
        try:
            reply = adapter.complete(messages, live=True)
            record["raw_model_output"] = sanitize(reply.text, secret)
            record["raw_response"] = sanitize(reply.raw_response, secret)
            record["response_metadata"] = sanitize(reply.details, secret)
            parsed = parse_model_json(reply.text)
            record["parsed_result"] = parsed
            actual = validate_result(parsed, case["input"]["candidate_response"], project_root)
            record["validated_result"] = actual
            record["contract_valid"] = True
            record["comparison"] = compare_results(actual, expected)
            record["outcome"] = qualification_outcome(True, record["comparison"])
        except AdapterError as exc:
            record["raw_response"] = exc.raw_response
            record["response_metadata"] = exc.details
            record["error"] = {"category": "adapter", "kind": exc.kind, "details": exc.details}
        except ModelParseError:
            record["error"] = {"category": "parse", "kind": "malformed_model_json"}
        except ContractError:
            # No raw exception text is logged: paths/strings may be model-controlled.
            record["error"] = {"category": "contract", "kind": "contract_invalid_result"}
        if record["error"]:
            record["outcome"] = qualification_outcome(False, None)
        record["latency_seconds"] = time.perf_counter() - case_timer
        records.append(record)
    elapsed = time.perf_counter() - timer
    report = {"report_version": "1.2", "metadata": {
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model, "backend_host": urlsplit(config.base_url).hostname, "timeout_seconds": config.timeout,
        "temperature": 0, "max_tokens": config.max_tokens,
        "reasoning_config": config.reasoning, "reasoning_effort_config": config.reasoning_effort,
        "synthetic_only": True,
        "case_ids": [case["id"] for case in cases],
        "specification_sha256": hashlib.sha256(builder.specification.encode("utf-8")).hexdigest(),
        "metrics_policy": "Agreements use all attempts; HF precision/recall use valid responses only; zero denominators are null. Full match includes rationales and list order after source-ref normalization."},
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
