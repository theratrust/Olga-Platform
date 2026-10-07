"""Isolated DEV soak orchestration; no runtime bot integration or persistence ports."""
import asyncio
import hashlib
import json
import os
import subprocess
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from services import coaching_generator
from services.conversation_benchmark import ROOT, BenchmarkConfig, load_scenarios, _observe
from services.evaluation import runtime as method_runtime
from services.quality_evaluation import runtime as quality_runtime
from services.generator_diagnostics import diagnostic_metadata
from .overnight_ab_metrics import summarize, validate_candidate_id

BASELINE_COMMIT="176cb07c0941ffb53c5d34f99e9cb86def6ada59"
BASELINE_SOURCE_SHA256="f319b7b333f880a818d419f88035226b0c907e8cc70da872a20ecee8c2c08284"
BASELINE_MANIFEST="artifacts/evaluation/conversation-benchmark/baselines/20261005T212212329540Z_generator_baseline_manifest.json"
BASELINE_MANIFEST_SHA256="12ac835868102e94aaa3fefe235b9d812b6706774b66662f6bf2ce49c6d97f92"
SCENARIO_IDS=["identity_after_relocation","work_and_autonomy","partner_influence","dont_know_space","repeated_uncertainty","stuckness_and_action"]


def utc():return datetime.now(timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()
def variant_order(trial,candidate_id="CANDIDATE_A"):
    validate_candidate_id(candidate_id)
    return ("BASELINE",candidate_id) if trial%2 else (candidate_id,"BASELINE")


def validate_trials(n):
    if type(n)is not int or not 5<=n<=10:raise ValueError("Paired trials must be 5..10")


def load_variants(baseline_source=None,candidate_id="CANDIDATE_A"):
    validate_candidate_id(candidate_id)
    source=Path(baseline_source).read_bytes() if baseline_source else subprocess.check_output(
        ["git","show",BASELINE_COMMIT+":prompts/coaching.py"],cwd=ROOT,stderr=subprocess.DEVNULL)
    if sha(source)!=BASELINE_SOURCE_SHA256:raise ValueError("Pinned baseline mismatch")
    candidate=(ROOT/"prompts/coaching.py").read_bytes()
    # Baseline-only worktrees must support offline tooling validation too.
    if candidate!=source:
        start=candidate.index("Форма ответа и движение разговора:".encode())
        end=candidate.index("9. Говори спокойно".encode(),start)
        if candidate[:start]+candidate[end:]!=source:raise ValueError("Unexpected candidate difference")
    modules={}
    for name,content in [("BASELINE",source),(candidate_id,candidate)]:
        module=types.ModuleType("isolated_"+name)
        exec(compile(content,"<pinned_"+name+">","exec"),module.__dict__)
        modules[name]=module
    return modules,{"baseline_commit":BASELINE_COMMIT,"baseline_prompt_sha256":sha(source),
        "candidate_id":candidate_id,"candidate_prompt_sha256":sha(candidate),"candidate_tests_sha256":sha((ROOT/"tests/test_dev_conversation_benchmark.py").read_bytes())}


def verify_baseline():
    p=ROOT/BASELINE_MANIFEST
    if sha(p.read_bytes())!=BASELINE_MANIFEST_SHA256:raise ValueError("Baseline manifest mismatch")
    m=json.loads(p.read_text())
    for s in m["source_artifacts"]:
        if sha((ROOT/s["relative_path"]).read_bytes())!=s["sha256"]:raise ValueError("Baseline artifact mismatch")
    return m


def project_diagnostic(d):
    def number(x):return x if type(x)is int and x>=0 else None
    reasons=d.get("reasoning_fields",{})
    lengths=[number(r.get("character_length")) for r in reasons.values() if type(r)is dict]
    lengths=[v for v in lengths if v is not None]
    usage=d.get("usage",{})
    return {"call_succeeded":d.get("provider_call_succeeded") is True,
        "choices_count":number(d.get("choices_count")),"selected_choice_index":number(d.get("selected_choice_index")),
        "finish_reason":d.get("finish_reason") if d.get("finish_reason") in {"stop","length","tool_calls","function_call","content_filter","other"} else None,
        "content_present":d.get("content_present") is True,
        "content_type":d.get("content_type") if d.get("content_type") in {"missing","NoneType","str","int","bool","float","list","dict","tuple","other"} else "other",
        "content_length":number(d.get("content_character_length")),
        "content_whitespace_only":d.get("content_whitespace_only") if type(d.get("content_whitespace_only"))is bool else None,
        "reasoning_present":any(r.get("present") is True for r in reasons.values() if type(r)is dict),
        "reasoning_length":max(lengths) if lengths else None,
        "refusal_present":d.get("refusal_present") is True,"tool_calls_count":number(d.get("tool_calls_count")),
        **{f:number(usage.get(f)) for f in ["prompt_tokens","completion_tokens","reasoning_tokens","total_tokens"]},
        "model_match":d.get("response_model_matches_request") is True,
        "latency_ms":d.get("latency_ms") if type(d.get("latency_ms"))in (int,float) and d["latency_ms"]>=0 else None,
        "safe_error_category":d.get("provider_error_category") if d.get("provider_error_category") in {"timeout","transport_error","http_error","provider_error","response_shape_error"} else None,
        "http_status":d.get("http_status") if type(d.get("http_status"))is int and 100<=d["http_status"]<=599 else None}


def classify_failure(d):
    if not d["call_succeeded"]:return "PROVIDER_OR_TRANSPORT_FAILURE"
    if d["choices_count"]==0:return "ZERO_CHOICES"
    if not d["content_present"] or d["content_type"] not in {"str","NoneType"}:return "UNEXPECTED_RESPONSE_SHAPE"
    if d["refusal_present"] or (d["tool_calls_count"] or 0)>0:return "REFUSAL_OR_TOOL_ONLY"
    if d["reasoning_present"]:return "REASONING_PRESENT_FINAL_EMPTY"
    if d["finish_reason"]=="length":return "LENGTH_TERMINATED_EMPTY"
    if d["content_type"]=="NoneType":return "EMPTY_NULL_CONTENT"
    if d["content_length"]==0:return "EMPTY_STRING_CONTENT"
    if d["content_whitespace_only"]:return "WHITESPACE_ONLY_CONTENT"
    return "OTHER_SAFE_DIAGNOSTIC_PATTERN"


class EventWriter:
    def __init__(self,path,secret=None):
        self.path=Path(path);self.secret=secret
        fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        self.stream=os.fdopen(fd,"w",encoding="utf-8")
    def emit(self,event):
        text=json.dumps(event,ensure_ascii=False,allow_nan=False)
        if self.secret and self.secret in text:raise ValueError("Secret in safe projection")
        self.stream.write(text+"\n");self.stream.flush();os.fsync(self.stream.fileno())
    def close(self):self.stream.close()


def recover_events(path):
    # A partial final write is ignored; malformed complete/interior lines fail closed.
    raw=Path(path).read_bytes();lines=raw.splitlines(keepends=True);events=[]
    for i,line in enumerate(lines):
        if not line.endswith(b"\n") and i==len(lines)-1:break
        events.append(json.loads(line))
    return events


def fingerprint_sources():
    paths=list((ROOT/"services").rglob("*.py"))+list((ROOT/"prompts").rglob("*.py"))+list((ROOT/"knowledge").rglob("*.md"))
    paths += [ROOT/"tests/dev_conversation_scenarios.json",ROOT/"tests/test_dev_conversation_benchmark.py",ROOT/"tests/run_dev_overnight_ab_soak.py"]
    return {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sorted(set(paths))}


def check_sources(fingerprint):
    if any(sha((ROOT/p).read_bytes())!=h for p,h in fingerprint.items()):raise ValueError("Frozen source drift")


async def execute_trials(scenarios,modules,config,trials,client,emit,*,mconfig=None,qconfig=None,method_adapter=None,quality_adapter=None,source_check=lambda:None,candidate_id="CANDIDATE_A"):
    validate_candidate_id(candidate_id)
    validate_trials(trials)
    mconfig=mconfig or method_runtime.ShadowConfig(enabled=True)
    qconfig=qconfig or quality_runtime.QualityShadowConfig(enabled=True)
    for trial in range(1,trials+1):
        for variant in variant_order(trial,candidate_id):
            for scenario in scenarios:
                source_check();correlation=uuid4().hex;history=[]
                instruction=modules[variant].build_coaching_prompt(first_name="Тест",archetype=scenario["archetype"])
                common={"trial":trial,"variant":variant,"scenario_id":scenario["id"]}
                emit({"event":"scenario_start","timestamp":utc(),**common,"correlation_hash":sha(correlation.encode())})
                completed=True
                for turn,user in enumerate(scenario["turns"],1):
                    source_check();history.append({"role":"user","content":user});context=[dict(x) for x in history[-20:]]
                    rawdiag=[];timer=time.perf_counter();error=None
                    try:
                        candidate=await coaching_generator.generate_candidate(client,config.model,
                            coaching_generator.build_messages(instruction,context),diagnostic_observer=rawdiag.append)
                        failure="empty_response" if candidate is None or type(candidate)is str and not candidate.strip() else "response_format_error" if type(candidate)is not str else None
                    except Exception as exc:
                        error=exc;failure="generator_exception"
                    diagnostic=project_diagnostic(rawdiag[0] if rawdiag else diagnostic_metadata(None,config.model,False,error,(time.perf_counter()-timer)*1000))
                    success=failure is None
                    event={"event":"generator_attempt","timestamp":utc(),**common,"turn":turn,"success":success,
                        "failure_kind":failure,"failure_classification":None if success else classify_failure(diagnostic),"diagnostic":diagnostic,
                        "user_input_hash":sha(user.encode()),"assistant_output_hash":sha(candidate.encode()) if success else None}
                    # Durable generator evidence before either evaluator runs.
                    emit(event)
                    if not success:completed=False;break
                    history.append({"role":"assistant","content":candidate})
                    method=_observe(method_runtime.evaluate_candidate_shadow,context,user,candidate,
                        quality=False,config=mconfig,adapter=method_adapter,session_id=correlation)
                    quality=_observe(quality_runtime.evaluate_candidate_quality_shadow,context,user,candidate,
                        quality=True,config=qconfig,adapter=quality_adapter,session_id=correlation)
                    emit({"event":"evaluators","timestamp":utc(),**common,"turn":turn,"methodology":method,"quality":quality})
                emit({"event":"scenario_end","timestamp":utc(),**common,"completed":completed})
            emit({"event":"variant_end","timestamp":utc(),"trial":trial,"variant":variant})
        emit({"event":"trial_end","timestamp":utc(),"trial":trial})


def write_exclusive(path,value,json_file=True):
    text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n" if json_file else value
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        stream.write(text);stream.flush();os.fsync(stream.fileno())


async def run_soak(config=BenchmarkConfig(),trials=10,*,live=False,baseline_source=None,run_id=None,candidate_id=None):
    if live and candidate_id is None:raise ValueError("Explicit live candidate identity required")
    candidate_id=validate_candidate_id(candidate_id or "CANDIDATE")
    config.validate();validate_trials(trials);verify_baseline()
    modules,identity=load_variants(baseline_source,candidate_id)
    scenarios=load_scenarios()
    if [s["id"] for s in scenarios]!=SCENARIO_IDS or any(len(s["turns"])!=6 for s in scenarios):raise ValueError("Scenario mismatch")
    if not live:return {"dry_run":True,"candidate_id":candidate_id,"paired_trials":trials,"variants":2,"scenarios_per_variant":6,
        "maximum_generator_turns":trials*72,"generator_max_tokens":350,"network_calls":0,"credential_lookups":0,"artifact_writes":0}
    if not method_runtime.is_dev_runtime():raise ValueError("DEV identity required")
    if config.model!="z-ai/glm-5.2" or config.base_url!="https://openrouter.ai/api/v1" or config.api_key_env!="OPENROUTER_API_KEY" or config.generator_max_tokens!=350 or config.timeout!=60:
        raise ValueError("Frozen soak settings required")
    key=os.environ.get(config.api_key_env)
    if not key or not key.strip():raise ValueError("Missing credential")
    from openai import AsyncOpenAI
    client=AsyncOpenAI(base_url=config.base_url,api_key=key,timeout=config.timeout)
    # No added call retries: shared service and SDK policy match the benchmark.
    sources=fingerprint_sources();started=utc()
    if run_id is None:run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+"_"+uuid4().hex
    if not all(c.isascii() and (c.isalnum() or c in "_-") for c in run_id) or not 1<=len(run_id)<=100:raise ValueError("Invalid run identifier")
    directory=ROOT/"artifacts/evaluation/overnight-ab"
    if directory.resolve()!=directory:raise ValueError("Symlink output")
    directory.mkdir(parents=True,exist_ok=True)
    prefix=directory/run_id
    events_path=Path(str(prefix)+".events.jsonl");writer=EventWriter(events_path,key)
    metadata={**identity,"scenario_file_sha256":sha((ROOT/"tests/dev_conversation_scenarios.json").read_bytes()),
        "candidate_working_tree_fingerprint":sha(json.dumps(sources,sort_keys=True).encode()),"source_fingerprints":sources,
        "baseline_manifest_sha256":BASELINE_MANIFEST_SHA256,"model":"z-ai/glm-5.2","generator_max_tokens":350,
        "timeout":60,"backend_host":"openrouter.ai","methodology_model":"z-ai/glm-5.2","quality_model":"z-ai/glm-5.2",
        "evaluator_max_tokens":4000,"evaluator_reasoning_effort":"low","paired_trials":trials,
        "historical_candidate_a":{"generator_calls":33,"empty_responses":4,"excluded_from_soak_estimates":True}}
    write_exclusive(str(prefix)+".status.json",{"pid":os.getpid(),"status":"running","started_at":started,"run_id":run_id})
    complete=False;status="interrupted";safe_error=None
    writer.emit({"event":"run_start","timestamp":started,"metadata":metadata})
    try:
        await execute_trials(scenarios,modules,config,trials,client,writer.emit,source_check=lambda:check_sources(sources),candidate_id=candidate_id)
        check_sources(sources);verify_baseline();complete=True;status="completed"
    except (Exception,asyncio.CancelledError):
        status="stopped";safe_error="source_or_infrastructure_error"
    finally:
        finished=utc()
        writer.emit({"event":"run_end","timestamp":finished,"completion_status":status,"safe_error":safe_error})
        writer.close()
        await client.close()
        events=recover_events(events_path)
        summary=summarize(events,complete=complete,candidate_id=candidate_id)
        report={"report_version":"1.0","synthetic_only":True,"run_id":run_id,"started_at":started,"finished_at":finished,
            "completion_status":status,"completed_trials":sum(e["event"]=="trial_end" for e in events),"metadata":metadata,
            "event_file":events_path.name,"event_file_sha256":sha(events_path.read_bytes()),"analysis":summary}
        write_exclusive(str(prefix)+".aggregate.json",report)
        lines=["# DEV overnight A/B soak", "", "Completion: "+status,
               "Reliability: "+summary["decision"]["generator_reliability"],"Coaching quality: "+summary["decision"]["coaching_quality"],""]
        for v in ["BASELINE",candidate_id]:
            x=summary["variants"][v];g=x["generator"];q=x["coaching"]["quality"];m=x["coaching"]["methodology"]
            lines.extend([v+": "+str(g["attempts"])+" generator attempts; "+str(g["failures"])+" failures; rate "+str(g["failure_rate"]),
                "Quality: "+json.dumps(q["overall_counts"])+"; Q03 "+str(q["q03_count"])+"; low non-repetition "+str(q["dimension_le_1_counts"]["non_repetition"]),
                "Methodology: "+str(m["hard_fail_count"])+" hard fails; pass rate "+str(m["pass_rate"]),""])
        lines.append("Observational evaluator evidence; no automatic significance or routing claim. See aggregate JSON for paired results and diagnostic distributions.")
        write_exclusive(str(prefix)+".summary.md","\n".join(lines)+"\n",False)
        write_exclusive(str(prefix)+".terminal.json",{"status":status,"finished_at":finished,"completed_trials":report["completed_trials"]})
    return {"completion_status":status,"run_id":run_id}
