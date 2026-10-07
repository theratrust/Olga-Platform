"""Offline soak isolation/recovery/privacy tests; never live provider calls."""
import asyncio
import ast
import copy
import hashlib
import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as Obj
from urllib import request
import pytest
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services import overnight_ab_soak as soak
from services.overnight_ab_metrics import summarize,paired_metrics,wilson
from services.conversation_benchmark import BenchmarkConfig,load_scenarios
from services.generator_diagnostics import diagnostic_metadata


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a,**k):raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    monkeypatch.setattr(request.OpenerDirector,"open",forbidden)


def fake_observe(function,context,user,candidate,*,quality,**kwargs):
    status={"first_pass_contract_valid":True,"retry_attempted":False,"retry_recovered":False,"final_contract_valid":True,
            "latency_ms":1,"evaluator_error_kind":None,"first_pass_error_kind":None,"insufficient_context":False}
    if quality:status.update(scores={d:2 for d in ["contextual_specificity","progression","non_repetition","naturalness","question_quality","proportionality"]},quality_flags=[],overall_quality="strong")
    else:status.update(hard_fail=False,hf_ids=[],scores={d:2 for d in ["client_authorship","grounding","hypothesis_freedom","respectful_style"]},overall="pass",decision="accept")
    return status


class Client:
    def __init__(self,fail_at=()):
        self.calls=[];self.fail_at=set(fail_at);self.chat=Obj(completions=Obj(create=self.create))
    async def create(self,**kwargs):
        self.calls.append(copy.deepcopy(kwargs));content=None if len(self.calls) in self.fail_at else "PRIVATE_ASSISTANT"
        return Obj(model="z-ai/glm-5.2",choices=[Obj(message=Obj(content=content,reasoning="PRIVATE_REASONING"),finish_reason="stop")],usage=Obj(prompt_tokens=20,completion_tokens=5,total_tokens=25))


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.setattr(soak,"_observe",fake_observe)
    def run(fail_at=(),candidate_id="CANDIDATE_A"):
        client=Client(fail_at);events=[];modules,_=soak.load_variants(candidate_id=candidate_id)
        asyncio.run(soak.execute_trials(load_scenarios(),modules,BenchmarkConfig("z-ai/glm-5.2"),5,client,events.append,candidate_id=candidate_id))
        return client,events
    return run


def test_pinned_source_candidate_exact_intended_block_and_no_mutation(tmp_path):
    candidate=(ROOT/"prompts/coaching.py").read_bytes();modules,identity=soak.load_variants()
    baseline=subprocess.check_output(["git","show",soak.BASELINE_COMMIT+":prompts/coaching.py"],cwd=ROOT)
    assert hashlib.sha256(baseline).hexdigest()==identity["baseline_prompt_sha256"]==soak.BASELINE_SOURCE_SHA256
    assert identity["candidate_prompt_sha256"]==hashlib.sha256(candidate).hexdigest()
    if candidate!=baseline:
        start=candidate.index("Форма ответа и движение разговора:".encode());end=candidate.index("9. Говори спокойно".encode(),start)
        assert candidate[:start]+candidate[end:]==baseline
    baseline_instruction=modules["BASELINE"].build_coaching_prompt(first_name="Тест",archetype="Полутень")
    candidate_instruction=modules["CANDIDATE_A"].build_coaching_prompt(first_name="Тест",archetype="Полутень")
    assert (baseline_instruction==candidate_instruction)==(candidate==baseline)
    path=tmp_path/"baseline.py";path.write_bytes(baseline)
    assert soak.load_variants(path)[1]==identity
    assert (ROOT/"prompts/coaching.py").read_bytes()==candidate


def test_baseline_snapshot_mismatch_rejected(tmp_path):
    p=tmp_path/"source.py";p.write_text("PRIVATE")
    with pytest.raises(ValueError):soak.load_variants(p)


@pytest.mark.parametrize("trial,order",[(1,("BASELINE","CANDIDATE_A")),(2,("CANDIDATE_A","BASELINE")),(3,("BASELINE","CANDIDATE_A")),(10,("CANDIDATE_A","BASELINE"))])
def test_alternating_order(trial,order):assert soak.variant_order(trial)==order


@pytest.mark.parametrize("n",[0,1,4,11,100,True,5.0])
def test_trial_cap(n):
    with pytest.raises(ValueError):soak.validate_trials(n)


@pytest.mark.parametrize("n",[5,10])
def test_allowed_trial_counts(n):soak.validate_trials(n)


def test_history_request_settings_diag_each_attempt_and_raw_absence(experiment):
    client,events=experiment();generators=[e for e in events if e["event"]=="generator_attempt"]
    assert len(client.calls)==len(generators)==360
    scenarios=load_scenarios()
    for idx,call in enumerate(client.calls):
        scenario=scenarios[(idx//6)%6];turn=idx%6
        assert call["model"]=="z-ai/glm-5.2" and call["max_tokens"]==350
        assert call["extra_headers"]=={"HTTP-Referer":"https://telegram.org","X-Title":"Olga Coaching Bot"}
        expected=[]
        for i in range(turn+1):
            expected.append({"role":"user","content":scenario["turns"][i]})
            if i<turn:expected.append({"role":"assistant","content":"PRIVATE_ASSISTANT"})
        assert call["messages"][1:]==expected
    starts=[e for e in events if e["event"]=="scenario_start"]
    assert len({s["correlation_hash"] for s in starts})==60
    assert [s["variant"] for s in starts[0:12:6]]==["BASELINE","CANDIDATE_A"]
    assert [s["variant"] for s in starts[12:24:6]]==["CANDIDATE_A","BASELINE"]
    text=json.dumps(events,ensure_ascii=False)
    assert "PRIVATE_ASSISTANT" not in text and "PRIVATE_REASONING" not in text
    for s in scenarios:
        for user in s["turns"]:assert user not in text
    assert len([e for e in events if e["event"]=="evaluators"])==360
    assert generators[0]["diagnostic"]["reasoning_present"]
    assert generators[0]["diagnostic"]["reasoning_length"]==len("PRIVATE_REASONING")


def test_failure_only_aborts_scenario_no_retry_next_trial_continues(experiment):
    client,events=experiment([2]);gens=[e for e in events if e["event"]=="generator_attempt"]
    failed=[e for e in gens if not e["success"]]
    assert len(failed)==1 and failed[0]["turn"]==2 and failed[0]["scenario_id"]=="identity_after_relocation"
    assert failed[0]["failure_classification"]=="REASONING_PRESENT_FINAL_EMPTY"
    assert len(client.calls)==356 # Four remaining scripted turns skipped, no retry.
    assert any(e["trial"]==1 and e["scenario_id"]=="work_and_autonomy" for e in gens)
    assert any(e["trial"]==2 and e["scenario_id"]=="identity_after_relocation" for e in gens)
    assert len([e for e in events if e["event"]=="trial_end"])==5
    assert not any(e["event"]=="evaluators" and (e["trial"],e["variant"],e["scenario_id"],e["turn"])==(1,"BASELINE","identity_after_relocation",2) for e in events)


def test_durable_jsonl_flush_recovery_and_exclusive(tmp_path):
    path=tmp_path/"events.jsonl";writer=soak.EventWriter(path)
    writer.emit({"event":"safe","number":1})
    assert soak.recover_events(path)==[{"event":"safe","number":1}]
    writer.emit({"event":"safe","number":2});writer.close()
    with path.open('ab') as f:f.write(b'{"partial":')
    assert len(soak.recover_events(path))==2
    with pytest.raises(FileExistsError):soak.EventWriter(path)
    path.write_bytes(b'bad\n')
    with pytest.raises(ValueError):soak.recover_events(path)


def test_event_writer_rejects_secret_before_write(tmp_path):
    path=tmp_path/"events.jsonl";writer=soak.EventWriter(path,"PRIVATE_KEY")
    with pytest.raises(ValueError):writer.emit({"event":"PRIVATE_KEY"})
    writer.close();assert path.read_bytes()==b''


def test_paired_matching_only_success_and_valid_observations(experiment):
    _,events=experiment([2]);paired=paired_metrics(events)
    assert paired["quality_pairs"]==175 # 180 pairs less failed turn plus four skipped.
    assert paired["comparisons"]["non_repetition"]["unchanged"]==175
    altered=copy.deepcopy(events)
    e=next(e for e in altered if e["event"]=="evaluators" and e["variant"]=="CANDIDATE_A")
    e["quality"]["final_contract_valid"]=False
    assert paired_metrics(altered)["quality_pairs"]==174


def test_aggregates_deterministic_rates_failure_breakdowns_and_conclusions(experiment):
    _,events=experiment([2]);a=summarize(events,True);assert a==summarize(copy.deepcopy(events),True)
    g=a["variants"]["BASELINE"]["generator"]
    assert g["attempts"]==176 and g["failures"]==1 and g["empty_response_count"]==1
    assert g["by_turn"]["2"]["failures"]==1 and g["by_scenario"]["identity_after_relocation"]["failures"]==1
    assert g["by_trial"]["1"]["failures"]==1
    assert a["variants"]["CANDIDATE_A"]["coaching"]["methodology"]["overall_counts"]["pass"]==180
    assert a["decision"]["generator_reliability"]=="CANDIDATE_A_RELIABILITY_SIMILAR"
    assert a["paired"]["comparisons"]["Q03_REPETITIVE_STRUCTURE"]["unchanged"]==175


def test_empty_metrics_zero_denominators_and_intervals():
    r=summarize([],False)
    assert r["reliability_comparison"]["relative_risk"] is None
    assert r["decision"]["generator_reliability"]=="RELIABILITY_INCONCLUSIVE"
    assert r["decision"]["coaching_quality"]=="QUALITY_INCONCLUSIVE"
    assert wilson(0,0) is None
    assert 0<=wilson(0,10)[0]<=wilson(0,10)[1]<=1


@pytest.mark.parametrize("changes,expected",[
 ({"call_succeeded":False},"PROVIDER_OR_TRANSPORT_FAILURE"),
 ({"choices_count":0},"ZERO_CHOICES"),
 ({"content_present":False},"UNEXPECTED_RESPONSE_SHAPE"),
 ({"refusal_present":True},"REFUSAL_OR_TOOL_ONLY"),
 ({"reasoning_present":True,"finish_reason":"length"},"REASONING_PRESENT_FINAL_EMPTY"),
 ({"finish_reason":"length"},"LENGTH_TERMINATED_EMPTY"),
 ({"content_type":"NoneType"},"EMPTY_NULL_CONTENT"),
 ({"content_length":0},"EMPTY_STRING_CONTENT"),
 ({"content_length":3,"content_whitespace_only":True},"WHITESPACE_ONLY_CONTENT"),
 ({"content_length":3,"content_whitespace_only":False},"OTHER_SAFE_DIAGNOSTIC_PATTERN"),
])
def test_documented_failure_precedence(changes,expected):
    d={"call_succeeded":True,"choices_count":1,"content_present":True,"content_type":"str","content_length":0,
       "refusal_present":False,"tool_calls_count":0,"reasoning_present":False,"finish_reason":"stop","content_whitespace_only":True}
    d.update(changes);assert soak.classify_failure(d)==expected


def cli():
    spec=importlib.util.spec_from_file_location("soak_cli",ROOT/"tests/run_dev_overnight_ab_soak.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_default_dry_run_zero_credentials_network_artifacts(monkeypatch,capsys):
    original=soak.os.environ.get
    def get(k,*a):
        if k=="OPENROUTER_API_KEY":pytest.fail("Credential lookup")
        return original(k,*a)
    monkeypatch.setattr(soak.os.environ,"get",get)
    monkeypatch.setattr(soak.method_runtime,"is_dev_runtime",lambda:pytest.fail("Dry guard"))
    monkeypatch.setattr(soak,"EventWriter",lambda *a:pytest.fail("Artifact write"))
    monkeypatch.setattr(soak.coaching_generator,"generate_candidate",lambda *a,**k:pytest.fail("Generator call"))
    assert cli().main([])==0
    r=json.loads(capsys.readouterr().out)
    assert r["candidate_id"]=="CANDIDATE"
    assert r["dry_run"] and r["maximum_generator_turns"]==720 and r["generator_max_tokens"]==350
    assert r["network_calls"]==r["credential_lookups"]==r["artifact_writes"]==0


def test_live_cli_requires_explicit_config():assert cli().main(["--live"])==2


def test_guard_rejects_live_before_credentials(monkeypatch):
    monkeypatch.setattr(soak.method_runtime,"is_dev_runtime",lambda:False)
    original=soak.os.environ.get
    def get(k,*a):
        if k=="OPENROUTER_API_KEY":pytest.fail("Credential lookup")
        return original(k,*a)
    monkeypatch.setattr(soak.os.environ,"get",get)
    with pytest.raises(ValueError):asyncio.run(soak.run_soak(BenchmarkConfig("z-ai/glm-5.2","https://openrouter.ai/api/v1"),live=True,candidate_id="CANDIDATE_A"))


def test_no_db_telegram_ports_or_imports():
    for name in ['services/overnight_ab_soak.py','services/overnight_ab_metrics.py','tests/run_dev_overnight_ab_soak.py']:
        source=(ROOT/name).read_text()
        for node in ast.walk(ast.parse(source)):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            assert all(n.split('.')[0] not in {'database','aiogram','telegram','handlers','bot','sqlite3','aiosqlite'} for n in names)
        for port in ['getUpdates','add_chat_message','get_recent_history','clear_chat_history','create_pending_draft','FSMContext']:assert port not in source



def test_paired_directions_and_null_exclusions(experiment):
    _,events=experiment()
    candidate=[e for e in events if e["event"]=="evaluators" and e["variant"]=="CANDIDATE_A"]
    candidate[0]["quality"]["scores"]["non_repetition"]=1
    candidate[0]["quality"]["quality_flags"]=["Q03_REPETITIVE_STRUCTURE"]
    candidate[0]["quality"]["overall_quality"]="acceptable"
    candidate[1]["quality"]["scores"]["question_quality"]=None
    r=paired_metrics(events)
    assert r["comparisons"]["non_repetition"]["worsened"]==1
    assert r["comparisons"]["Q03_REPETITIVE_STRUCTURE"]["worsened"]==1
    assert r["comparisons"]["overall_quality"]["worsened"]==1
    assert r["comparisons"]["question_quality"]["excluded_null_or_insufficient"]==1
    assert r["comparisons"]["non_repetition"]["candidate_minus_baseline_mean"]==-1/180


def test_source_drift_stops_experiment_before_next_call(tmp_path,monkeypatch):
    monkeypatch.setattr(soak,"ROOT",tmp_path)
    p=tmp_path/"frozen.py";p.write_bytes(b'one')
    fingerprint={"frozen.py":hashlib.sha256(p.read_bytes()).hexdigest()}
    soak.check_sources(fingerprint);p.write_bytes(b'two')
    with pytest.raises(ValueError):soak.check_sources(fingerprint)


@pytest.mark.parametrize("candidate_id",["CANDIDATE_A","CANDIDATE_B"])
def test_live_lifecycle_mocked_artifacts_and_privacy(tmp_path,monkeypatch,candidate_id):
    import types
    modules,identity=soak.load_variants(candidate_id=candidate_id)
    (tmp_path/"tests").mkdir();(tmp_path/"prompts").mkdir()
    for name in ['prompts/coaching.py','tests/test_dev_conversation_benchmark.py','tests/dev_conversation_scenarios.json','tests/run_dev_overnight_ab_soak.py']:
        (tmp_path/name).write_bytes((ROOT/name).read_bytes())
    monkeypatch.setattr(soak,"ROOT",tmp_path)
    monkeypatch.setattr(soak,"load_variants",lambda source,candidate_id="CANDIDATE_A":(modules,identity))
    monkeypatch.setattr(soak,"verify_baseline",lambda:{})
    monkeypatch.setattr(soak.method_runtime,"is_dev_runtime",lambda:True)
    monkeypatch.setattr(soak,"_observe",fake_observe)
    monkeypatch.setenv("OPENROUTER_API_KEY","PRIVATE_KEY")
    class Owned(Client):
        async def close(self):self.closed=True
    client=Owned()
    monkeypatch.setitem(sys.modules,"openai",types.SimpleNamespace(AsyncOpenAI=lambda **kwargs:client))
    config=BenchmarkConfig('z-ai/glm-5.2','https://openrouter.ai/api/v1','OPENROUTER_API_KEY')
    r=asyncio.run(soak.run_soak(config,5,live=True,run_id='test_unique',candidate_id=candidate_id))
    assert r['completion_status']=='completed' and client.closed
    directory=tmp_path/'artifacts/evaluation/overnight-ab'
    events=soak.recover_events(directory/'test_unique.events.jsonl')
    assert len([e for e in events if e['event']=='generator_attempt'])==360
    report=json.loads((directory/'test_unique.aggregate.json').read_text())
    assert report['completed_trials']==5 and report['analysis']['paired']['quality_pairs']==180
    assert report['completion_status']=='completed'
    assert report['metadata']['candidate_id']==candidate_id
    assert report['metadata']['candidate_prompt_sha256']==identity['candidate_prompt_sha256']
    assert set(report['analysis']['variants'])=={'BASELINE',candidate_id}
    assert candidate_id in report['analysis']['paired']
    assert json.loads((directory/'test_unique.status.json').read_text())['pid']>0
    assert json.loads((directory/'test_unique.terminal.json').read_text())['status']=='completed'
    assert (directory/'test_unique.summary.md').is_file()
    text=''.join(p.read_text() for p in directory.iterdir())
    for private in ['PRIVATE_KEY','PRIVATE_ASSISTANT','PRIVATE_REASONING']:
        assert private not in text
    for scenario in load_scenarios():
        for user in scenario['turns']:assert user not in text



@pytest.mark.parametrize("candidate_id",["CANDIDATE_A","CANDIDATE_B"])
def test_configured_identity_in_order_prompt_and_events(experiment,candidate_id):
    assert soak.variant_order(1,candidate_id)==("BASELINE",candidate_id)
    assert soak.variant_order(2,candidate_id)==(candidate_id,"BASELINE")
    modules,identity=soak.load_variants(candidate_id=candidate_id)
    assert set(modules)=={"BASELINE",candidate_id}
    assert identity["candidate_id"]==candidate_id
    assert identity["candidate_prompt_sha256"]==hashlib.sha256((ROOT/"prompts/coaching.py").read_bytes()).hexdigest()
    _,events=experiment(candidate_id=candidate_id)
    assert {e["variant"] for e in events if "variant" in e}=={"BASELINE",candidate_id}
    result=summarize(events,True,candidate_id)
    assert set(result["variants"])=={"BASELINE",candidate_id}
    assert result["paired"]["quality_pairs"]==180 and candidate_id in result["paired"]
    assert result["decision"]["generator_reliability"]==candidate_id+"_RELIABILITY_SIMILAR"
    assert result["decision"]["coaching_quality"]==candidate_id+"_QUALITY_MIXED"


def test_equivalent_events_same_metrics_under_candidate_rename(experiment):
    _,events=experiment([2])
    renamed=copy.deepcopy(events)
    for e in renamed:
        if e.get("variant")=="CANDIDATE_A":e["variant"]="CANDIDATE_B"
    a=summarize(events,True)
    b=summarize(renamed,True,"CANDIDATE_B")
    def normalize(v):
        if type(v)is dict:return {(k.replace("CANDIDATE_B","CANDIDATE_A") if type(k)is str else k):normalize(x) for k,x in v.items()}
        if type(v)is list:return [normalize(x) for x in v]
        return v.replace("CANDIDATE_B","CANDIDATE_A") if type(v)is str else v
    assert normalize(b)==a


def test_metric_formula_and_threshold_ast_unchanged():
    # Fingerprint of ALL original metric function ASTs. Normalize identity-only
    # parameters/lookups/labels back to their historical A representation.
    class IdentityOnly(ast.NodeTransformer):
        def visit_FunctionDef(self,node):
            if node.args.args and node.args.args[-1].arg=="candidate_id":
                node.args.args.pop();node.args.defaults.pop()
            node.body=[n for n in node.body if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                and isinstance(n.value.func,ast.Name) and n.value.func.id=="validate_candidate_id")]
            return self.generic_visit(node)
        def visit_Name(self,node):
            if node.id=="candidate_id":return ast.Constant("CANDIDATE_A")
            return node
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id=="paired_metrics" and len(node.args)>1:node.args=node.args[:1]
            return self.generic_visit(node)
        def visit_JoinedStr(self,node):
            node=self.generic_visit(node);parts=[]
            for item in node.values:
                if isinstance(item,ast.Constant):parts.append(item.value)
                elif isinstance(item,ast.FormattedValue) and isinstance(item.value,ast.Constant):parts.append(item.value.value)
                else:return node
            return ast.Constant(''.join(parts))
    tree=ast.parse((ROOT/'services/overnight_ab_metrics.py').read_text())
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name!='validate_candidate_id']
    normalized=ast.dump(IdentityOnly().visit(ast.Module(body=functions,type_ignores=[])),include_attributes=False)
    assert hashlib.sha256(normalized.encode()).hexdigest()=='239e0cf880eead4c2d5e49461166bea9152988e07a385bfc94864f211c2fee40'


@pytest.mark.parametrize("candidate_id",["BASELINE","candidate_b","",None,"CANDIDATE_B\nPRIVATE","A"*65])
def test_invalid_candidate_identity(candidate_id):
    with pytest.raises(ValueError):soak.variant_order(1,candidate_id)


def test_live_cli_requires_identity_before_runner(monkeypatch):
    m=cli();monkeypatch.setattr(m,"run_soak",lambda *a,**k:pytest.fail("Runner called"))
    assert m.main(["--live","--model","z-ai/glm-5.2","--base-url","https://openrouter.ai/api/v1","--api-key-env","OPENROUTER_API_KEY"])==2


def test_candidate_b_dry_run_no_credentials(monkeypatch,capsys):
    original=soak.os.environ.get
    def get(k,*args):
        if k=='OPENROUTER_API_KEY':pytest.fail("Credential lookup")
        return original(k,*args)
    monkeypatch.setattr(soak.os.environ,'get',get)
    assert cli().main(['--candidate-id','CANDIDATE_B'])==0
    r=json.loads(capsys.readouterr().out)
    assert r['candidate_id']=='CANDIDATE_B' and r['dry_run']
    assert r['network_calls']==r['credential_lookups']==r['artifact_writes']==0


def test_historical_candidate_a_artifact_analysis_compatible():
    prefix=ROOT/'artifacts/evaluation/overnight-ab/20261006T051532563683Z_37af6684fcd541ef831e0d4f7c1533de'
    aggregate=Path(str(prefix)+'.aggregate.json')
    if not aggregate.exists():pytest.skip('Historical private DEV evidence unavailable')
    r=json.loads(aggregate.read_text())
    events=soak.recover_events(Path(str(prefix)+'.events.jsonl'))
    assert json.loads(json.dumps(summarize(events,True)))==r['analysis']



@pytest.mark.parametrize("mode",["baseline","shape_block","unrelated_change"])
def test_source_loading_baseline_checkpoint_and_existing_difference_guard(tmp_path,monkeypatch,mode):
    baseline=subprocess.check_output(["git","show",soak.BASELINE_COMMIT+":prompts/coaching.py"],cwd=ROOT)
    (tmp_path/"prompts").mkdir();(tmp_path/"tests").mkdir()
    snapshot=tmp_path/"baseline.py";snapshot.write_bytes(baseline)
    candidate=baseline
    if mode=="shape_block":
        candidate=baseline.replace("9. Говори спокойно".encode(),"Форма ответа и движение разговора:\n\n9. Говори спокойно".encode(),1)
    elif mode=="unrelated_change":candidate=baseline+b'\n# unrelated change\n'
    (tmp_path/"prompts/coaching.py").write_bytes(candidate)
    (tmp_path/"tests/test_dev_conversation_benchmark.py").write_text("# synthetic fixture")
    monkeypatch.setattr(soak,"ROOT",tmp_path)
    if mode=="unrelated_change":
        with pytest.raises(ValueError):soak.load_variants(snapshot,"CANDIDATE")
    else:
        modules,identity=soak.load_variants(snapshot,"CANDIDATE")
        assert identity["candidate_prompt_sha256"]==hashlib.sha256(candidate).hexdigest()
        assert set(modules)=={"BASELINE","CANDIDATE"}
