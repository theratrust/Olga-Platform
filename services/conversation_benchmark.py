"""Synthetic DEV conversation benchmark, without Telegram, FSM or persistence ports."""
import copy
import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from services import coaching_generator
from services.evaluation import runtime as methodology_runtime
from services.quality_evaluation import runtime as quality_runtime
from services.quality_evaluation.contract import DIMENSIONS, FLAG_DIMENSIONS
from services.model_qualification_adapter import ModelConfig, ERROR_KINDS, sanitize, backend_host
from .conversation_benchmark_metrics import calculate_metrics

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = "synthetic_dev_conversation_benchmark"
STATUS_FIELDS = ("first_pass_contract_valid", "retry_attempted", "retry_recovered", "final_contract_valid")
SAFE_ERRORS = ERROR_KINDS | {"unexpected_exception", "malformed_model_json", "malformed_json", "contract_invalid_result",
    "contract_invalid_output", "configuration_or_runtime_error", "dev_identity_rejected", "observer_failure", "generator_error"}


def _require(ok):
    if not ok:
        raise ValueError("Invalid benchmark schema or configuration")


def _unique(pairs):
    result = {}
    for key,value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Nonstandard JSON constant")


def validate_scenario(s):
    _require(type(s) is dict and set(s) == {"id","title","synthetic","provenance","archetype","turns"})
    _require(type(s["id"]) is str and re.fullmatch("[a-z][a-z0-9_]{0,63}", s["id"]) is not None)
    _require(s["synthetic"] is True and s["provenance"] == PROVENANCE)
    for field in ("title", "archetype"):
        _require(type(s[field]) is str and bool(s[field].strip()) and re.search("[А-Яа-яЁё]", s[field]) is not None)
    _require(type(s["turns"]) is list and 5 <= len(s["turns"]) <= 8)
    _require(all(type(t) is str and t.strip() and re.search("[А-Яа-яЁё]", t) is not None for t in s["turns"]))
    return copy.deepcopy(s)


def load_scenarios(path=None):
    path = ROOT / "tests/dev_conversation_scenarios.json" if path is None else Path(path)
    corpus = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique, parse_constant=_invalid_constant)
    _require(type(corpus) is dict and set(corpus) == {"schema_version","language","synthetic","provenance","scenarios"})
    _require(corpus["schema_version"] == "1.0" and corpus["language"] == "ru" and corpus["synthetic"] is True and corpus["provenance"] == PROVENANCE)
    _require(type(corpus["scenarios"]) is list and len(corpus["scenarios"]) >= 6)
    scenarios = [validate_scenario(s) for s in corpus["scenarios"]]
    _require(len({s["id"] for s in scenarios}) == len(scenarios))
    return scenarios


def select_scenarios(scenarios, ids=None, maximum=None):
    ids = list(ids or [])
    _require(len(ids) == len(set(ids)) and not set(ids)-{s["id"] for s in scenarios})
    _require(maximum is None or type(maximum) is int and maximum > 0)
    selected = [s for s in scenarios if not ids or s["id"] in ids]
    return selected[:maximum] if maximum is not None else selected


@dataclass(frozen=True)
class BenchmarkConfig:
    model: str = "offline-plan"
    base_url: str = "https://offline.invalid/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    timeout: float = 60.0
    generator_max_tokens: int = 350

    def validate(self):
        ModelConfig(self.model, self.base_url, self.timeout, self.api_key_env, self.generator_max_tokens).validate()
        return self


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _project(observation, quality):
    # Project only whitelisted typed aggregates; ignore raw runtime result/attempts.
    source = observation["log"] if type(observation) is dict and type(observation.get("log")) is dict else {}
    record = {f: source.get(f) is True for f in STATUS_FIELDS}
    record.update(latency_ms=source.get("latency_ms", 0),
                  evaluator_error_kind=source.get("evaluator_error_kind"), first_pass_error_kind=source.get("first_pass_error_kind"))
    for field in ("evaluator_error_kind", "first_pass_error_kind"):
        if record[field] is not None and record[field] not in SAFE_ERRORS:
            record[field] = "observer_failure"
    _require(type(record["latency_ms"]) in (int,float) and math.isfinite(record["latency_ms"]) and record["latency_ms"] >= 0)
    record["insufficient_context"] = source.get("insufficient_context") if type(source.get("insufficient_context")) is bool else None
    if quality:
        record.update(overall_quality=source.get("overall_quality"), scores=copy.deepcopy(source.get("scores")), quality_flags=copy.deepcopy(source.get("quality_flags", [])))
        labels, dimensions, flags = {"strong","acceptable","weak","insufficient_context"}, set(DIMENSIONS), set(FLAG_DIMENSIONS)
        _require(record["overall_quality"] is None or record["overall_quality"] in labels)
        _require(type(record["quality_flags"]) is list and all(type(f) is str and f in flags for f in record["quality_flags"]))
    else:
        record.update(hard_fail=source.get("hard_fail"), overall=source.get("overall"), decision=source.get("decision"),
                      scores=copy.deepcopy(source.get("scores")), hf_ids=copy.deepcopy(source.get("violations", [])))
        dimensions = {"client_authorship","grounding","hypothesis_freedom","respectful_style"}
        _require(record["hard_fail"] is None or type(record["hard_fail"]) is bool)
        _require(record["overall"] in (None,"pass","fail","review","insufficient_context"))
        _require(record["decision"] in (None,"accept","retry","escalate","insufficient_context"))
        _require(type(record["hf_ids"]) is list and all(type(f) is str and f in {f"HF{i:02d}" for i in range(1,9)} for f in record["hf_ids"]))
    scores = record["scores"]
    _require(scores is None or type(scores) is dict and set(scores) == dimensions and all(v is None or type(v) is int and v in (0,1,2) for v in scores.values()))
    if record["final_contract_valid"]:
        _require(scores is not None and type(record["insufficient_context"]) is bool)
        _require(record["overall_quality"] is not None if quality else type(record["hard_fail"]) is bool and record["overall"] is not None and record["decision"] is not None)
    if not source:
        record["evaluator_error_kind"] = "observer_failure"
    return record


def _observe(function, context, user, candidate, *, quality, config, adapter, session_id):
    try:
        return _project(function(copy.deepcopy(context), user, candidate, config=config, adapter=adapter, session_id=session_id), quality)
    except Exception:
        return _project({"log": {"evaluator_error_kind": "observer_failure"}}, quality)


def _generator_error(exc):
    name = type(exc).__name__
    if isinstance(exc, TimeoutError) or name == "APITimeoutError": return "timeout"
    if name == "APIConnectionError": return "transport_error"
    if hasattr(exc, "status_code"): return "http_error"
    return "generator_error"


def _model_metadata(config, *, generator=False):
    model = config.model
    return {"model": model, "backend_host": backend_host(config.base_url), "timeout_seconds": config.timeout,
            "max_tokens": config.generator_max_tokens if generator else config.max_tokens,
            **({} if generator else {"reasoning_effort": config.reasoning_effort,
               "reasoning_parameter_format": "reasoning" if isinstance(config, methodology_runtime.ShadowConfig) else "reasoning_effort"})}


async def run_benchmark(scenarios, config=BenchmarkConfig(), *, live=False, client=None,
                        methodology_config=None, quality_config=None, methodology_adapter=None, quality_adapter=None):
    config.validate()
    scenarios = [validate_scenario(s) for s in scenarios]
    _require(len({s["id"] for s in scenarios}) == len(scenarios) and bool(scenarios))
    mconfig = methodology_config or methodology_runtime.ShadowConfig(enabled=True)
    qconfig = quality_config or quality_runtime.QualityShadowConfig(enabled=True)
    _require(mconfig.enabled is True and qconfig.enabled is True)
    mconfig.adapter_config(); qconfig.adapter_config()
    # Validate all local prompt sources without looking up credentials.
    methodology_runtime.EvaluatorPromptBuilder()
    quality_runtime.QualityPromptBuilder()
    for s in scenarios:
        instruction = coaching_generator.build_system_instruction(first_name="Тест", archetype=s["archetype"])
        coaching_generator.build_messages(instruction, [{"role":"user","content":s["turns"][0]}])
    if live is not True:
        return {"dry_run": True, "scenario_count": len(scenarios), "turn_count": sum(len(s["turns"]) for s in scenarios),
                "network_calls": 0, "credential_lookups": 0, "artifact_writes": 0}
    _require(methodology_runtime.is_dev_runtime())
    key = os.environ.get(config.api_key_env)
    evaluator_key = os.environ.get("OPENROUTER_API_KEY")
    _require(type(key) is str and bool(key.strip()) and type(evaluator_key) is str and bool(evaluator_key.strip()))
    owned_client = client is None
    if owned_client:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url=config.base_url, api_key=key, timeout=config.timeout)
    started = datetime.now(timezone.utc).isoformat()
    records = []
    try:
        for scenario in scenarios:
            correlation = uuid4().hex
            history = []
            record = {"scenario_id": scenario["id"], "correlation_hash": sha(correlation), "planned_turns": len(scenario["turns"]),
                      "completed": False, "turns": []}
            instruction = coaching_generator.build_system_instruction(first_name="Тест", archetype=scenario["archetype"])
            for number,user in enumerate(scenario["turns"],1):
                history.append({"role":"user","content":user})
                context = copy.deepcopy(history[-20:])
                messages = coaching_generator.build_messages(instruction, context)
                turn = {"turn_number": number, "user_input_hash": sha(user), "assistant_output_hash": None,
                        "generator": {"success": False, "error_kind": None, "latency_ms": 0}, "methodology": None, "quality": None}
                timer = time.perf_counter()
                try:
                    candidate = await coaching_generator.generate_candidate(client, config.model, messages, max_tokens=config.generator_max_tokens)
                    if candidate is None or type(candidate) is str and not candidate.strip():
                        turn["generator"]["error_kind"] = "empty_response"
                    elif type(candidate) is not str:
                        turn["generator"]["error_kind"] = "response_format_error"
                    else:
                        turn["generator"]["success"] = True
                except Exception as exc:
                    turn["generator"]["error_kind"] = _generator_error(exc)
                turn["generator"]["latency_ms"] = round((time.perf_counter()-timer)*1000,3)
                record["turns"].append(turn)
                if not turn["generator"]["success"]:
                    break  # No invented assistant turn; abort this scenario, continue next.
                turn["assistant_output_hash"] = sha(candidate)
                history.append({"role":"assistant","content":candidate})
                turn["methodology"] = _observe(methodology_runtime.evaluate_candidate_shadow, context, user, candidate,
                    quality=False, config=mconfig, adapter=methodology_adapter, session_id=correlation)
                turn["quality"] = _observe(quality_runtime.evaluate_candidate_quality_shadow, context, user, candidate,
                    quality=True, config=qconfig, adapter=quality_adapter, session_id=correlation)
            record["completed"] = len(record["turns"]) == record["planned_turns"] and all(t["generator"]["success"] for t in record["turns"])
            records.append(record)
    finally:
        if owned_client:
            await client.close()
    report = {"report_version": "1.0", "dry_run": False, "synthetic_only": True,
              "scenario_ids": [s["id"] for s in scenarios], "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
              "metadata": {"generator": _model_metadata(config, generator=True), "methodology": _model_metadata(mconfig), "quality": _model_metadata(qconfig),
                "scenario_manifest_sha256": sha(json.dumps(scenarios, ensure_ascii=False, sort_keys=True, separators=(",",":"))),
                "generator_prompt_sha256": sha((ROOT/"prompts/coaching.py").read_text()),
                "methodology_specification_sha256": sha(methodology_runtime.EvaluatorPromptBuilder().specification),
                "quality_specification_sha256": sha(quality_runtime.QualityPromptBuilder().specification)},
              "scenarios": records, "metrics": calculate_metrics(records)}
    return sanitize(sanitize(report, key), evaluator_key)


def write_report(report, *, project_root=ROOT):
    _require(report.get("dry_run") is False and report.get("synthetic_only") is True)
    # Refuse added fields: even caller-supplied records cannot add raw text containers.
    _require(set(report) == {"report_version","dry_run","synthetic_only","scenario_ids","started_at","finished_at","metadata","scenarios","metrics"})
    _require(report["report_version"] == "1.0")
    metadata = report["metadata"]
    _require(type(metadata) is dict and set(metadata) == {"generator","methodology","quality","scenario_manifest_sha256","generator_prompt_sha256","methodology_specification_sha256","quality_specification_sha256"})
    def is_hash(value):
        return type(value) is str and re.fullmatch("[0-9a-f]{64}",value) is not None
    for field in ("scenario_manifest_sha256","generator_prompt_sha256","methodology_specification_sha256","quality_specification_sha256"):
        _require(is_hash(metadata[field]))
    for field in ("generator","methodology","quality"):
        item = metadata[field]
        expected = {"model","backend_host","timeout_seconds","max_tokens"}
        if field != "generator": expected |= {"reasoning_effort","reasoning_parameter_format"}
        _require(type(item) is dict and set(item) == expected)
        _require(type(item["model"]) is str and re.fullmatch("[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}",item["model"]) is not None)
        _require(type(item["backend_host"]) is str and re.fullmatch("[A-Za-z0-9.:-]+",item["backend_host"]) is not None)
        _require(type(item["timeout_seconds"]) in (int,float) and math.isfinite(item["timeout_seconds"]) and item["timeout_seconds"] > 0)
        _require(type(item["max_tokens"]) is int and item["max_tokens"] > 0)
        if field != "generator":
            _require(item["reasoning_effort"] in ("none","minimal","low","medium","high"))
            _require(item["reasoning_parameter_format"] in ("reasoning","reasoning_effort"))
    for field in ("started_at","finished_at"):
        _require(type(report[field]) is str and datetime.fromisoformat(report[field]).tzinfo is not None)
    _require(report["scenario_ids"] == [s["scenario_id"] for s in report["scenarios"]])
    _require(len(set(report["scenario_ids"])) == len(report["scenario_ids"]))
    for scenario in report["scenarios"]:
        _require(set(scenario) == {"scenario_id","correlation_hash","planned_turns","completed","turns"})
        _require(type(scenario["scenario_id"]) is str and re.fullmatch("[a-z][a-z0-9_]{0,63}",scenario["scenario_id"]) is not None)
        _require(is_hash(scenario["correlation_hash"]))
        _require(type(scenario["planned_turns"]) is int and 5 <= scenario["planned_turns"] <= 8)
        _require(type(scenario["completed"]) is bool)
        for position, turn in enumerate(scenario["turns"],1):
            _require(turn["turn_number"] == position and type(turn["turn_number"]) is int)
            _require(is_hash(turn["user_input_hash"]))
            _require(turn["assistant_output_hash"] is None or is_hash(turn["assistant_output_hash"]))
            _require(set(turn) == {"turn_number","user_input_hash","assistant_output_hash","generator","methodology","quality"})
            _require(set(turn["generator"]) == {"success","error_kind","latency_ms"})
            generator = turn["generator"]
            _require(type(generator["success"]) is bool and generator["error_kind"] in SAFE_ERRORS | {None})
            _require(type(generator["latency_ms"]) in (int,float) and math.isfinite(generator["latency_ms"]) and generator["latency_ms"] >= 0)
            for field, quality in (("methodology",False),("quality",True)):
                record = turn[field]
                if record is not None:
                    # Reprojection also checks scalar values, scores and allowed labels.
                    log = dict(record)
                    if not quality: log["violations"] = log.pop("hf_ids")
                    _require(record == _project({"log":log},quality))
    # Recompute all descriptive metrics; no arbitrary caller metrics survive.
    _require(report["metrics"] == calculate_metrics(report["scenarios"]))
    root = Path(project_root).resolve()
    directory = root / "artifacts/evaluation/conversation-benchmark"
    _require(directory.resolve() == directory)
    directory.mkdir(parents=True,exist_ok=True)
    _require(directory.resolve() == directory)
    path = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid4().hex + ".json")
    with path.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    return path
