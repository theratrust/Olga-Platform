"""Synthetic fake-model tests; never Telegram, database or live provider calls."""
import asyncio
import ast
import copy
import importlib.util
import json
import math
import socket
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock
from urllib import request
import pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from services import coaching_generator
from services import conversation_benchmark as benchmark
from services.conversation_benchmark_metrics import calculate_metrics, latency_stats, rate
from services.evaluation.model_adapter import ModelReply as MethodReply
from services.quality_evaluation.model_adapter import ModelReply as QualityReply, AdapterError

SCENARIOS = benchmark.load_scenarios()
CONFIG = benchmark.BenchmarkConfig("fake-generator","https://example.invalid/v1","BENCHMARK_TEST_KEY")
CANDIDATE = "Синтетический ответ."


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a,**k):
        raise AssertionError("Live network forbidden")
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    monkeypatch.setattr(request.OpenerDirector,"open",forbidden)
    monkeypatch.setenv("BENCHMARK_TEST_KEY","SYNTHETIC_GENERATOR_SECRET")
    monkeypatch.setenv("OPENROUTER_API_KEY","SYNTHETIC_EVALUATOR_SECRET")


class Client:
    def __init__(self,outputs=None):
        self.outputs = iter(outputs) if outputs is not None else None
        self.calls = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))
    async def create(self,**kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        value = next(self.outputs) if self.outputs is not None else CANDIDATE
        if isinstance(value,Exception): raise value
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=value))])


def method_result():
    return {"hard_fail":False,"violations":[],"scores":{"client_authorship":2,"grounding":2,"hypothesis_freedom":2,"respectful_style":2},
        "overall":"pass","decision":"accept","reason":"PRIVATE_METHOD_REASON",
        "source_refs":[{"path":"knowledge/method/метод_Ольги.md","section":"Не давать готовых решений","provenance":"direct_olga_confirmed"}],
        "insufficient_context":{"present":False,"items":[]}}


def quality_result(flags=(),null=False):
    value = {"scores":dict.fromkeys(benchmark.DIMENSIONS,2),"quality_flags":[],"overall_quality":"strong",
             "reason":"PRIVATE_QUALITY_REASON","insufficient_context":{"present":False,"items":[]}}
    for flag in flags:
        value["scores"][benchmark.FLAG_DIMENSIONS[flag]] = 1
        value["quality_flags"].append({"flag_id":flag,"evidence":CANDIDATE})
    if flags: value["overall_quality"] = "acceptable"
    if null:
        value["scores"]["non_repetition"] = None
        value["overall_quality"] = "insufficient_context"
        value["insufficient_context"] = {"present":True,"items":[{"dimensions":["non_repetition"],"missing":"PRIVATE_MISSING","reason":"PRIVATE_CONTEXT_REASON"}]}
    return value


class Evaluator:
    def __init__(self,quality=False,outputs=None):
        self.quality = quality
        self.outputs = iter(outputs) if outputs is not None else None
        self.calls = []
    def complete(self,messages,*,live=False):
        assert live is True
        self.calls.append(copy.deepcopy(messages))
        value = next(self.outputs) if self.outputs is not None else quality_result() if self.quality else method_result()
        if isinstance(value,Exception): raise value
        reply = QualityReply if self.quality else MethodReply
        return reply(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False),
                     "PRIVATE_PROVIDER_ENVELOPE SYNTHETIC_EVALUATOR_SECRET",{"reasoning":"PRIVATE_REASONING"})


def run(scenarios=None,client=None,method=None,quality=None):
    client,method,quality = client or Client(),method or Evaluator(),quality or Evaluator(True)
    report = asyncio.run(benchmark.run_benchmark(scenarios or SCENARIOS[:1],CONFIG,live=True,
        client=client,methodology_adapter=method,quality_adapter=quality))
    return report,client,method,quality


def cli():
    spec = importlib.util.spec_from_file_location("benchmark_cli",ROOT/"tests/run_dev_conversation_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_dry_run_zero_network_credentials_artifacts_sdk(monkeypatch,capsys):
    original = benchmark.os.environ.get
    def guarded(name,*args):
        if name in ("OPENROUTER_API_KEY","BENCHMARK_TEST_KEY"):
            pytest.fail("credential lookup during dry run")
        return original(name,*args)
    monkeypatch.setattr(benchmark.os.environ,"get",guarded)
    monkeypatch.setattr(benchmark.methodology_runtime,"is_dev_runtime",lambda:pytest.fail("DEV guard not needed for dry run"))
    monkeypatch.setattr(coaching_generator,"generate_candidate",lambda *a,**k:pytest.fail("generator called"))
    monkeypatch.setattr(benchmark.methodology_runtime,"evaluate_candidate_shadow",lambda *a,**k:pytest.fail("evaluator called"))
    monkeypatch.setattr(benchmark.quality_runtime,"evaluate_candidate_quality_shadow",lambda *a,**k:pytest.fail("evaluator called"))
    module = cli()
    monkeypatch.setattr(module,"write_report",lambda *a,**k:pytest.fail("artifact written"))
    assert module.main([]) == 0
    assert module.main(["--dry-run","--max-scenarios","1"]) == 0
    text = capsys.readouterr().out
    assert "DRY RUN: 6 scenarios / 36 turns" in text
    assert "zero credential lookups" in text
    result = asyncio.run(benchmark.run_benchmark(SCENARIOS))
    assert result == {"dry_run":True,"scenario_count":6,"turn_count":36,"network_calls":0,"credential_lookups":0,"artifact_writes":0}


def test_corpus_synthetic_russian_six_scenarios_36_turns():
    assert len(SCENARIOS) == 6 and sum(len(s["turns"]) for s in SCENARIOS) == 36
    for scenario in SCENARIOS:
        assert scenario["synthetic"] is True and scenario["provenance"] == benchmark.PROVENANCE
        assert benchmark.validate_scenario(scenario) == scenario
        assert "expected" not in scenario


@pytest.mark.parametrize("mutation",["unknown","provenance","synthetic","turn_count","turn_type","language","id","archetype"])
def test_scenario_schema_rejects_invalid(mutation):
    scenario = copy.deepcopy(SCENARIOS[0])
    if mutation == "unknown": scenario["expected"] = "strong"
    elif mutation == "provenance": scenario["provenance"] = "real"
    elif mutation == "synthetic": scenario["synthetic"] = False
    elif mutation == "turn_count": scenario["turns"] = scenario["turns"][:4]
    elif mutation == "turn_type": scenario["turns"][0] = {}
    elif mutation == "language": scenario["turns"][0] = "English only"
    elif mutation == "id": scenario["id"] = "../escape"
    else: scenario["archetype"] = ""
    with pytest.raises(ValueError): benchmark.validate_scenario(scenario)


@pytest.mark.parametrize("mutation",["duplicate","unknown_field","wrong_language","wrong_provenance","too_few","duplicate_json","nonstandard_json"])
def test_corpus_schema_strict(tmp_path,mutation):
    corpus = json.loads((ROOT/"tests/dev_conversation_scenarios.json").read_text())
    if mutation == "duplicate": corpus["scenarios"][1]["id"] = corpus["scenarios"][0]["id"]
    elif mutation == "unknown_field": corpus["raw_real_data"] = "x"
    elif mutation == "wrong_language": corpus["language"] = "en"
    elif mutation == "wrong_provenance": corpus["provenance"] = "other"
    elif mutation == "too_few": corpus["scenarios"] = corpus["scenarios"][:1]
    text = json.dumps(corpus,ensure_ascii=False)
    if mutation == "duplicate_json": text = text.replace('"schema_version": "1.0"','"schema_version": "1.0", "schema_version": "1.0"')
    elif mutation == "nonstandard_json": text = text.replace('"synthetic": true','"synthetic": NaN',1)
    path = tmp_path/"scenarios.json"
    path.write_text(text)
    with pytest.raises(ValueError): benchmark.load_scenarios(path)


@pytest.mark.parametrize("ids,maximum",[(["unknown"],None),([SCENARIOS[0]["id"]]*2,None),(None,0),(None,-1),(None,True)])
def test_unknown_duplicate_selection_rejected(ids,maximum):
    with pytest.raises(ValueError): benchmark.select_scenarios(SCENARIOS,ids,maximum)


def test_selection_preserves_corpus_order():
    assert benchmark.select_scenarios(SCENARIOS,[SCENARIOS[2]["id"],SCENARIOS[0]["id"]],1) == [SCENARIOS[0]]


@pytest.mark.parametrize("args",[["--live"],["--live","--model","fake"],["--live","--model","fake","--base-url","https://example.invalid/v1"]])
def test_live_cli_requires_explicit_config(args):
    assert cli().main(args) == 2


@pytest.mark.parametrize("missing",["BENCHMARK_TEST_KEY","OPENROUTER_API_KEY"])
def test_live_requires_both_credentials_before_generator(missing,monkeypatch):
    monkeypatch.delenv(missing)
    client = Client()
    with pytest.raises(ValueError): asyncio.run(benchmark.run_benchmark(SCENARIOS[:1],CONFIG,live=True,client=client))
    assert not client.calls


def test_dev_guard_blocks_live_before_credentials(monkeypatch):
    monkeypatch.setattr(benchmark.methodology_runtime,"is_dev_runtime",lambda:False)
    original = benchmark.os.environ.get
    def guarded(name,*args):
        assert name not in ("BENCHMARK_TEST_KEY","OPENROUTER_API_KEY")
        return original(name,*args)
    monkeypatch.setattr(benchmark.os.environ,"get",guarded)
    client = Client()
    with pytest.raises(ValueError): asyncio.run(benchmark.run_benchmark(SCENARIOS[:1],CONFIG,live=True,client=client))
    assert not client.calls


def test_shared_generator_exact_request_and_extraction():
    client = Client()
    instruction = coaching_generator.build_system_instruction(first_name="Тест",archetype="Полутень")
    from prompts.coaching import build_coaching_prompt
    assert instruction == build_coaching_prompt(first_name="Тест",archetype="Полутень")
    history = [{"role":"user","content":"Синтетическое сообщение."}]
    messages = coaching_generator.build_messages(instruction,history)
    assert messages == [{"role":"system","content":instruction}]+history
    assert asyncio.run(coaching_generator.generate_candidate(client,"fake",messages)) == CANDIDATE
    assert client.calls == [{"model":"fake","messages":messages,"max_tokens":350,
                            "extra_headers":{"HTTP-Referer":"https://telegram.org","X-Title":"Olga Coaching Bot"}}]


def test_benchmark_shared_path_history_fresh_scenarios_and_evaluators(monkeypatch):
    original = coaching_generator.generate_candidate
    shared_calls = []
    async def shared(*a,**k):
        shared_calls.append(True)
        return await original(*a,**k)
    monkeypatch.setattr(coaching_generator,"generate_candidate",shared)
    report,client,method,quality = run(SCENARIOS[:2])
    assert len(shared_calls) == len(client.calls) == len(method.calls) == len(quality.calls) == 12
    for scenario_index,scenario in enumerate(SCENARIOS[:2]):
        expected = []
        for turn,user in enumerate(scenario["turns"]):
            expected.append({"role":"user","content":user})
            payload = client.calls[scenario_index*6+turn]
            assert payload["messages"][1:] == expected[-20:]
            assert payload["model"] == CONFIG.model and payload["max_tokens"] == 350
            qinput = json.loads(quality.calls[scenario_index*6+turn][1]["content"].split("\n",1)[1])
            minput = json.loads(method.calls[scenario_index*6+turn][1]["content"].split("\n",1)[1])
            assert qinput["conversation_context"] == minput["conversation_context"] == expected[-20:]
            assert qinput["candidate_response"] == minput["candidate_response"] == CANDIDATE
            expected.append({"role":"assistant","content":CANDIDATE})
    assert report["scenarios"][0]["correlation_hash"] != report["scenarios"][1]["correlation_hash"]
    assert all(s["completed"] for s in report["scenarios"])
    assert report["metadata"]["methodology"]["reasoning_parameter_format"] == "reasoning"
    assert report["metadata"]["quality"]["reasoning_parameter_format"] == "reasoning_effort"


def test_no_database_telegram_fsm_ports_or_imports():
    files = ["services/conversation_benchmark.py","services/conversation_benchmark_metrics.py","services/coaching_generator.py","tests/run_dev_conversation_benchmark.py"]
    forbidden = {"database","aiogram","bot","handlers","sqlite3","aiosqlite","telegram"}
    for name in files:
        source = (ROOT/name).read_text()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node,ast.Import):
                assert all(alias.name.split('.')[0] not in forbidden for alias in node.names)
            elif isinstance(node,ast.ImportFrom):
                assert (node.module or '').split('.')[0] not in forbidden
        for port in ("add_chat_message","get_recent_history","clear_chat_history","create_pending_draft","getUpdates","FSMContext"):
            assert port not in source


@pytest.mark.parametrize("quality_failure",["malformed","empty","truncated","contract","provider"])
def test_existing_evaluator_retry_bounded(quality_failure):
    invalid = quality_result()
    del invalid["scores"]
    first = {"malformed":"{","empty":AdapterError("empty_response"),"truncated":AdapterError("truncated_response"),
             "contract":invalid,"provider":AdapterError("provider_error")}[quality_failure]
    qmodel = Evaluator(True,[first,quality_result()]+[quality_result()]*5) if quality_failure != "provider" else Evaluator(True,[first]+[quality_result()]*5)
    mmodel = Evaluator(False,["{",method_result()]+[method_result()]*5)
    report,_,method,quality = run(method=mmodel,quality=qmodel)
    turn = report["scenarios"][0]["turns"][0]
    assert len(method.calls) == 7 and turn["methodology"]["retry_recovered"]
    assert len(quality.calls) == (6 if quality_failure == "provider" else 7)
    assert turn["quality"]["retry_attempted"] == (quality_failure != "provider")
    assert turn["quality"]["retry_recovered"] == (quality_failure != "provider")


def test_evaluators_maximum_two_and_independent_failures():
    report,_,method,quality = run(method=Evaluator(False,["{","{"]+[method_result()]*5),
        quality=Evaluator(True,["{","{"]+[quality_result()]*5))
    assert len(method.calls) == len(quality.calls) == 7
    assert report["metrics"]["infrastructure"]["methodology_evaluator_failures"] == 1
    assert report["metrics"]["infrastructure"]["quality_evaluator_failures"] == 1
    assert report["scenarios"][0]["completed"]


@pytest.mark.parametrize("output,error",[(None,"empty_response"),(" ","empty_response"),({},"response_format_error"),(TimeoutError("PRIVATE_GENERATOR_ERROR"),"timeout"),(RuntimeError("SYNTHETIC_GENERATOR_SECRET"),"generator_error")])
def test_generator_failure_aborts_only_scenario(output,error):
    client = Client([output]+[CANDIDATE]*6)
    report,_,method,quality = run(SCENARIOS[:2],client=client)
    first,second = report["scenarios"]
    assert not first["completed"] and len(first["turns"]) == 1 and second["completed"]
    assert first["turns"][0]["generator"]["error_kind"] == error
    assert first["turns"][0]["methodology"] is first["turns"][0]["quality"] is None
    assert len(method.calls) == len(quality.calls) == 6
    assert report["metrics"]["skipped_turns_after_generator_failure"] == 5
    assert "PRIVATE_GENERATOR_ERROR" not in json.dumps(report)


def test_artifact_privacy_hashes_metadata_and_metrics(tmp_path):
    report,_,_,_ = run(quality=Evaluator(True,[quality_result(["Q03_REPETITIVE_STRUCTURE"])]*6))
    path = benchmark.write_report(report,project_root=tmp_path)
    text = path.read_text()
    for forbidden in (CANDIDATE,*SCENARIOS[0]["turns"],"PRIVATE_METHOD_REASON","PRIVATE_QUALITY_REASON","PRIVATE_PROVIDER_ENVELOPE","PRIVATE_REASONING","SYNTHETIC_GENERATOR_SECRET","SYNTHETIC_EVALUATOR_SECRET","OPENROUTER_API_KEY","extra_headers"):
        assert forbidden not in text
    data = json.loads(text)
    assert data["synthetic_only"] is True
    assert path.parent == tmp_path/"artifacts/evaluation/conversation-benchmark"
    assert len(data["scenarios"][0]["correlation_hash"]) == 64
    assert all(len(t["user_input_hash"]) == len(t["assistant_output_hash"]) == 64 for t in data["scenarios"][0]["turns"])
    assert data["metadata"]["generator"]["max_tokens"] == 350
    assert data["metrics"]["quality"]["q03_count"] == 6


@pytest.mark.parametrize("location",["report","metadata","generator_metadata","scenario","turn","generator","quality","metrics"])
def test_writer_rejects_extra_raw_fields(location,tmp_path):
    report,_,_,_ = run()
    target = {"report":report,"metadata":report["metadata"],"generator_metadata":report["metadata"]["generator"],
              "scenario":report["scenarios"][0],"turn":report["scenarios"][0]["turns"][0],
              "generator":report["scenarios"][0]["turns"][0]["generator"],
              "quality":report["scenarios"][0]["turns"][0]["quality"],"metrics":report["metrics"]}[location]
    target["raw_user_message"] = "PRIVATE_RAW_TEXT"
    with pytest.raises(ValueError): benchmark.write_report(report,project_root=tmp_path)
    assert not list(tmp_path.iterdir())


def test_dry_report_cannot_write(tmp_path):
    report = asyncio.run(benchmark.run_benchmark(SCENARIOS[:1]))
    with pytest.raises(ValueError): benchmark.write_report(report,project_root=tmp_path)
    assert not list(tmp_path.iterdir())


def test_artifact_symlink_rejected(tmp_path):
    outside = tmp_path/"outside"
    outside.mkdir()
    (tmp_path/"artifacts").symlink_to(outside,target_is_directory=True)
    report,_,_,_ = run()
    with pytest.raises(ValueError): benchmark.write_report(report,project_root=tmp_path)
    assert not list(outside.iterdir())


def test_aggregate_counts_distributions_recurrence_and_deterioration():
    q03,q04 = "Q03_REPETITIVE_STRUCTURE","Q04_LOW_PROGRESSION"
    outputs = [quality_result(),quality_result(),quality_result([q03,q04]),quality_result([q03,q04]),quality_result([q03]),quality_result(),
               quality_result(),quality_result(),quality_result(),quality_result(),quality_result(),quality_result([q03])]
    report,_,_,_ = run(SCENARIOS[:2],quality=Evaluator(True,outputs))
    metrics = report["metrics"]
    assert metrics["methodology"]["overall_counts"]["pass"] == 12
    assert metrics["methodology"]["decision_counts"]["accept"] == 12
    assert metrics["methodology"]["hard_fail_count"] == 0 and metrics["methodology"]["hard_fail_rate"] == 0
    assert all(n == 0 for n in metrics["methodology"]["hf_frequencies"].values())
    q = metrics["quality"]
    assert q["overall_counts"] == {"strong":8,"acceptable":4,"weak":0,"insufficient_context":0}
    assert q["q03_count"] == 4 and q["scenarios_containing_q03"] == 2
    assert q["consecutive_q03_pairs"] == 2
    assert q["dimension_le_1_counts"]["non_repetition"] == 4
    assert q["dimension_le_1_counts"]["progression"] == 2
    assert q["scenarios_with_non_repetition_le_1_twice"] == q["scenarios_with_progression_le_1_twice"] == 1
    assert q["dimension_distributions"]["non_repetition"] == {"0":0,"1":4,"2":8,"null":0}
    assert q["scenarios_with_late_deterioration"] == 2
    signal = q["weakness_analysis"]["flag:"+q03]
    assert signal["recurring_cross_scenario"]
    assert signal["repeated_within_scenario"] == [SCENARIOS[0]["id"]]
    assert signal["isolated_within_scenario"] == [SCENARIOS[1]["id"]]


def test_null_scores_not_low_and_no_deterioration_rank_for_insufficient():
    report,_,_,_ = run(quality=Evaluator(True,[quality_result(null=True)]*6))
    q = report["metrics"]["quality"]
    assert q["overall_counts"]["insufficient_context"] == 6
    assert q["dimension_distributions"]["non_repetition"]["null"] == 6
    assert q["dimension_le_1_counts"]["non_repetition"] == 0
    assert q["per_scenario"][0]["late_mean_lower_than_early"] is None
    assert q["per_scenario"][0]["last_overall_worse_than_first"] is None


@pytest.mark.parametrize("values,mean,median,p95",[([],None,None,None),([1],1,1,1),([1,2,3,4],2.5,2.5,4),(list(range(1,21)),10.5,10.5,19),([float('nan'),-1,float('inf'),2],2,2,2)])
def test_latency_percentiles(values,mean,median,p95):
    result = latency_stats(values)
    assert (result["mean_ms"],result["median_ms"],result["p95_ms"]) == (mean,median,p95)


def test_zero_denominators():
    metrics = calculate_metrics([])
    assert rate(0,0) is None
    assert metrics["methodology"]["hard_fail_rate"] is None
    for kind in ("methodology","quality"):
        assert metrics[kind]["reliability"]["final_valid_rate"] is None
        assert metrics[kind]["reliability"]["retry_recovery_rate"] is None


def test_chat_and_benchmark_both_import_shared_generator():
    chat = (ROOT/"handlers/chat.py").read_text()
    assert "from services.coaching_generator import build_system_instruction, build_messages, generate_candidate" in chat
    assert "await generate_candidate(ai_client, model_name, messages_payload)" in chat
    assert "chat.completions.create" not in chat
    assert "coaching_generator.generate_candidate" in (ROOT/"services/conversation_benchmark.py").read_text()


def test_generator_call_ast_matches_pre_extraction_git_version():
    import subprocess
    old = ast.parse(subprocess.check_output(["git","show","176cb07c0941ffb53c5d34f99e9cb86def6ada59^:handlers/chat.py"],cwd=ROOT).decode())
    shared = ast.parse((ROOT/"services/coaching_generator.py").read_text())
    def request(tree):
        return next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr == 'create')
    before,after = request(old),request(shared)
    before_fields = {k.arg: k.value for k in before.keywords}
    after_fields = {k.arg: k.value for k in after.keywords}
    assert set(before_fields) == set(after_fields) == {'model','messages','max_tokens','extra_headers'}
    assert ast.dump(before_fields['model']) == ast.dump(after_fields['model'])
    assert ast.dump(before_fields['extra_headers']) == ast.dump(after_fields['extra_headers'])
    assert before_fields['max_tokens'].value == coaching_generator.DEFAULT_MAX_TOKENS == 350


def test_nonzero_methodology_fail_review_context_and_quality_categories():
    fail = method_result()
    fail.update(hard_fail=True,overall="fail",decision="retry")
    fail["scores"]["client_authorship"] = 0
    fail["violations"] = [{"rule_id":"HF01","excerpt":CANDIDATE,"reason":"PRIVATE_FAIL_REASON","source_refs":copy.deepcopy(fail["source_refs"])}]
    escalate = copy.deepcopy(fail)
    escalate["violations"][0]["rule_id"] = "HF05"
    escalate["decision"] = "escalate"
    review = method_result()
    review.update(overall="review",decision="escalate")
    review["scores"]["client_authorship"] = 1
    gap = method_result()
    gap.update(overall="insufficient_context",decision="insufficient_context")
    gap["scores"]["grounding"] = None
    gap["insufficient_context"] = {"present":True,"items":[{"rule_ids":["HF08"],"missing":"PRIVATE_MISSING","reason":"PRIVATE_GAP_REASON"}]}
    weak = quality_result()
    weak["scores"]["progression"] = 0
    weak["overall_quality"] = "weak"
    report,_,_,_ = run(method=Evaluator(False,[fail,escalate,review,gap,method_result(),method_result()]),
        quality=Evaluator(True,[quality_result(),weak,quality_result(["Q05_GENERIC_QUESTION"]),quality_result(null=True),quality_result(),quality_result()]))
    m,q = report["metrics"]["methodology"],report["metrics"]["quality"]
    assert m["reliability"]["final_valid"] == q["reliability"]["final_valid"] == 6
    assert m["hard_fail_count"] == 2 and m["hard_fail_rate"] == pytest.approx(2/6)
    assert m["overall_counts"] == {"pass":2,"fail":2,"review":1,"insufficient_context":1}
    assert m["decision_counts"] == {"accept":2,"retry":1,"escalate":2,"insufficient_context":1}
    assert m["hf_frequencies"]["HF01"] == m["hf_frequencies"]["HF05"] == 1
    assert q["overall_counts"] == {"strong":3,"acceptable":1,"weak":1,"insufficient_context":1}
    assert q["dimension_le_1_counts"]["progression"] == q["dimension_le_1_counts"]["question_quality"] == 1
    assert q["flag_frequencies"]["Q05_GENERIC_QUESTION"] == 1
    assert q["dimension_distributions"]["progression"]["0"] == 1


def test_explicit_model_and_token_overrides_recorded_without_config_mutation():
    config = benchmark.BenchmarkConfig("explicit-generator","https://example.invalid/v1","BENCHMARK_TEST_KEY",25,175)
    method_config = benchmark.methodology_runtime.ShadowConfig(enabled=True,model="explicit-method")
    quality_config = benchmark.quality_runtime.QualityShadowConfig(enabled=True,model="explicit-quality")
    client = Client()
    report = asyncio.run(benchmark.run_benchmark(SCENARIOS[:1],config,live=True,client=client,
        methodology_config=method_config,quality_config=quality_config,
        methodology_adapter=Evaluator(),quality_adapter=Evaluator(True)))
    assert all(call["model"] == "explicit-generator" and call["max_tokens"] == 175 for call in client.calls)
    assert report["metadata"]["generator"]["timeout_seconds"] == 25
    assert report["metadata"]["methodology"]["model"] == "explicit-method"
    assert report["metadata"]["quality"]["model"] == "explicit-quality"
    assert method_config.max_tokens == quality_config.max_tokens == 4000
    assert method_config.reasoning_effort == quality_config.reasoning_effort == "low"
