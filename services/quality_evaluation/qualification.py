"""Offline planning and bounded synthetic quality model qualification."""
import copy
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .contract import PROJECT_ROOT, QualityContractError, load_corpus, validate_case, validate_result
from .model_adapter import AdapterError, ModelParseError, parse_model_json, sanitize, backend_host
from .metrics import calculate_metrics, compare_results, qualification_outcome
from .repair import contract_diagnostic, retry_eligible, retry_messages


def load_labeled_cases(project_root=PROJECT_ROOT):
    corpus = load_corpus(project_root=project_root)
    if len(corpus["cases"]) != 22:
        raise QualityContractError("Qualification requires the frozen 22-case quality corpus")
    return corpus["cases"]


def select_cases(cases, case_ids=None, max_cases=None):
    ids = list(case_ids or [])
    if len(ids) != len(set(ids)) or set(ids) - {c["id"] for c in cases}:
        raise ValueError("Unknown or duplicate case ID")
    if max_cases is not None and (type(max_cases) is not int or max_cases < 1):
        raise ValueError("max_cases must be positive")
    selected = [c for c in cases if not ids or c["id"] in ids]
    return selected[:max_cases] if max_cases is not None else selected


def _attempt(messages, adapter, case, expected, secret):
    record = {"raw_model_output": None, "raw_response": None, "response_metadata": None,
              "parsed_result": None, "validated_result": None, "contract_valid": False,
              "comparison": None, "error": None}
    start = time.perf_counter()
    try:
        reply = adapter.complete(messages, live=True)
        record.update(raw_model_output=sanitize(reply.text, secret), raw_response=sanitize(reply.raw_response, secret),
                      response_metadata=sanitize(reply.details, secret))
        parsed = parse_model_json(reply.text)
        record["parsed_result"] = parsed
        actual = validate_result(parsed, case["input"])
        record.update(validated_result=actual, contract_valid=True, comparison=compare_results(actual, expected))
    except AdapterError as exc:
        record.update(raw_response=sanitize(exc.raw_response, secret), response_metadata=sanitize(exc.details, secret),
                      error={"category": "provider_transport", "kind": exc.kind})
    except ModelParseError:
        record["error"] = {"category": "parse", "kind": "malformed_json"}
    except QualityContractError as exc:
        record["error"] = {"category": "contract", "kind": "contract_invalid_output", **contract_diagnostic(exc)}
    record["outcome"] = qualification_outcome(record["contract_valid"], record["comparison"])
    record["latency_seconds"] = time.perf_counter() - start
    return record


def qualify(cases, builder, adapter, config, *, live=False, secret=None):
    # Dry run does not read credentials, invoke adapter, or write artifacts.
    config.validate()
    prepared = [(c, validate_case(c), builder.build(c["input"])) for c in cases]
    if live is not True:
        return {"dry_run": True, "planned_cases": len(prepared), "network_calls": 0}
    key = os.environ.get(config.api_key_env)
    if not key or not key.strip():
        raise AdapterError("missing_api_key")
    secret = key
    start = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    records = []
    for case, expected, messages in prepared:
        first = _attempt(messages, adapter, case, expected, secret)
        retry = _attempt(retry_messages(messages, first["error"]), adapter, case, expected, secret) if retry_eligible(first) else None
        selected = retry if retry is not None else first
        record = copy.deepcopy(selected)
        record.update(case_id=case["id"], synthetic_input=copy.deepcopy(case["input"]), quality_gold_result=expected,
                      first_attempt=first, retry_attempt=retry, attempt_count=2 if retry else 1,
                      recovered=bool(retry and retry["contract_valid"]), final_selected_result=selected["validated_result"],
                      latency_seconds=first["latency_seconds"] + (retry["latency_seconds"] if retry else 0))
        records.append(record)
    return sanitize({"report_version": "1.0", "dry_run": False, "metadata": {
        "model": config.model, "backend_host": backend_host(config.base_url),
        "timeout_seconds": config.timeout, "max_tokens": config.max_tokens,
        "reasoning_effort_config": config.reasoning_effort, "temperature": 0,
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "synthetic_only": True, "max_attempts": 2, "case_ids": [c["id"] for c in cases],
        "specification_sha256": hashlib.sha256(builder.specification.encode()).hexdigest()},
        "cases": records, "metrics": calculate_metrics(records, time.perf_counter()-start)}, secret)


def write_report(report, *, project_root=PROJECT_ROOT, secret=None):
    if report.get("dry_run") is not False:
        raise ValueError("Dry run reports cannot be persisted")
    # Only canonical frozen synthetic cases can be written, never arbitrary input.
    gold = {c["id"]: c for c in load_labeled_cases(project_root)}
    for record in report["cases"]:
        case = gold[record["case_id"]]
        if record["synthetic_input"] != case["input"] or record["quality_gold_result"] != case["expected"]:
            raise ValueError("Artifact is not frozen synthetic corpus data")
    root = Path(project_root).resolve()
    destination = root / "artifacts/evaluation/quality"
    if destination.resolve() != destination:
        raise ValueError("Artifact directory redirects")
    destination.mkdir(parents=True, exist_ok=True)
    if destination.resolve() != destination:
        raise ValueError("Artifact directory redirects")
    path = destination / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex + ".json")
    with path.open("x", encoding="utf-8") as out:
        out.write(json.dumps(sanitize(report, secret), ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return path
