"""Offline provider-boundary diagnostics: fake objects only, no live calls."""
import asyncio
import ast
import importlib.util
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace as Obj
from urllib import request
import pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from services.coaching_generator import generate_candidate, build_messages, DEFAULT_MAX_TOKENS
from services.generator_diagnostics import diagnostic_metadata
from services.conversation_benchmark import BenchmarkConfig, load_scenarios


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a,**k): raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    monkeypatch.setattr(request.OpenerDirector,"open",forbidden)


class Client:
    def __init__(self,responses):
        self.responses=iter(responses);self.calls=[]
        self.chat=Obj(completions=Obj(create=self.create))
    async def create(self,**kwargs):
        self.calls.append(kwargs)
        value=next(self.responses)
        if isinstance(value,Exception): raise value
        return value


def response(content="PRIVATE_CONTENT",finish="stop",**extra):
    return Obj(choices=[Obj(index=0,finish_reason=finish,message=Obj(content=content,**extra))],
               model="fake-model",usage=Obj(prompt_tokens=10,completion_tokens=4,total_tokens=14,
               completion_tokens_details=Obj(reasoning_tokens=3)))


class APIConnectionError(Exception): pass
class APIStatusError(Exception):
    status_code=429


CASES=[
    (response(),None,[]),
    (response(""),None,["content_empty_string"]),
    (response("   "),None,["content_whitespace_only"]),
    (response(None),None,["content_null"]),
    (Obj(choices=[],model="fake-model"),IndexError,["zero_choices"]),
    (response("",finish="length"),None,["content_empty_string","finish_reason_length"]),
    (response("",reasoning="PRIVATE_REASONING"),None,["reasoning_without_final_content"]),
    (Obj(choices=[Obj(message=Obj(),finish_reason="stop")]),AttributeError,["unexpected_response_shape"]),
    (APIConnectionError("PRIVATE_PROVIDER_ERROR SECRET"),APIConnectionError,["provider_call_failed"]),
    (response(["PRIVATE_UNEXPECTED_CONTENT"]),None,["unexpected_content_type"]),
]


@pytest.mark.parametrize("value,exception,signals",CASES)
def test_metadata_and_original_return_exception_equivalence(value,exception,signals):
    # Compare the unchanged extraction boundary with instrumented and ordinary calls.
    async def before(client):
        r=await client.chat.completions.create(model="fake-model",messages=[],max_tokens=350,
            extra_headers={"HTTP-Referer":"https://telegram.org","X-Title":"Olga Coaching Bot"})
        return r.choices[0].message.content
    records=[];clients=[Client([value]) for _ in range(3)]
    operations=[before(clients[0]),generate_candidate(clients[1],"fake-model",[]),
                generate_candidate(clients[2],"fake-model",[],diagnostic_observer=records.append)]
    results=[]
    for operation in operations:
        if exception:
            with pytest.raises(exception) as exc: asyncio.run(operation)
            if isinstance(value,Exception): assert exc.value is value
        else:
            results.append(asyncio.run(operation))
    if not exception:
        assert results[0] is results[1] is results[2] is value.choices[0].message.content
    assert clients[0].calls==clients[1].calls==clients[2].calls
    assert clients[2].calls[0]["max_tokens"]==DEFAULT_MAX_TOKENS==350
    assert len(records)==1
    record=records[0]
    assert all(signal in record["signals"] for signal in signals)
    assert record["provider_call_succeeded"] == (not isinstance(value,Exception))
    assert record["latency_ms"] >= 0
    text=json.dumps(record)
    for private in ["PRIVATE_CONTENT","PRIVATE_REASONING","PRIVATE_PROVIDER_ERROR","SECRET","PRIVATE_UNEXPECTED_CONTENT"]:
        assert private not in text


@pytest.mark.parametrize("content,present,kind,length,white",[
    (None,True,"NoneType",None,None),("",True,"str",0,True),("   ",True,"str",3,True),
    ("PRIVATE",True,"str",7,False),
])
def test_content_scalar_metadata(content,present,kind,length,white):
    r=diagnostic_metadata(response(content),"fake-model",True,None,1)
    assert (r["content_present"],r["content_type"],r["content_character_length"],r["content_whitespace_only"])==(present,kind,length,white)


def test_reasoning_refusal_tools_usage_projection():
    r=diagnostic_metadata(response("",reasoning_content="PRIVATE",reasoning_details=[{"text":"HIDDEN"}],
        refusal="PRIVATE_REFUSAL",tool_calls=[{"arguments":"PRIVATE_TOOL"}]),"fake-model",True,None,2)
    assert r["reasoning_fields"]["reasoning_content"]=={"present":True,"character_length":7}
    assert r["reasoning_fields"]["reasoning_details"]=={"present":True,"character_length":6}
    assert r["refusal_present"] and r["tool_calls_present"] and r["tool_calls_count"]==1
    assert r["usage"]=={"prompt_tokens":10,"completion_tokens":4,"total_tokens":14,"reasoning_tokens":3}
    assert r["response_model"]=="fake-model" and r["response_model_matches_request"]
    assert "PRIVATE" not in json.dumps(r) and "HIDDEN" not in json.dumps(r)


@pytest.mark.parametrize("error,kind,status",[(TimeoutError("PRIVATE"),"timeout",None),
    (APIConnectionError("PRIVATE"),"transport_error",None),(APIStatusError("PRIVATE"),"http_error",429),
    (RuntimeError("PRIVATE"),"provider_error",None)])
def test_safe_exception_category(error,kind,status):
    r=diagnostic_metadata(None,"fake-model",False,error,4)
    assert r["provider_error_category"]==kind and r["http_status"]==status
    assert "PRIVATE" not in json.dumps(r)


def test_provider_controlled_metadata_cannot_emit_free_text():
    value=response();value.model="PRIVATE_SECRET";value.choices[0].finish_reason="PRIVATE_FINISH"
    value.usage.prompt_tokens="PRIVATE_TOKENS"
    r=diagnostic_metadata(value,"fake-model",True,None,1)
    assert r["response_model"]=="other_model" and r["finish_reason"]=="other"
    assert r["usage"]["prompt_tokens"] is None and "PRIVATE" not in json.dumps(r)


@pytest.mark.parametrize("value",[response(),response(None),Obj(choices=[])])
def test_diagnostic_callback_failure_does_not_change_behavior(value):
    def bad(record): raise RuntimeError("Observer failure")
    if not value.choices:
        with pytest.raises(IndexError): asyncio.run(generate_candidate(Client([value]),"fake-model",[],diagnostic_observer=bad))
    else:
        assert asyncio.run(generate_candidate(Client([value]),"fake-model",[],diagnostic_observer=bad)) is value.choices[0].message.content


def test_metadata_access_failure_does_not_change_return():
    class Bad:
        choices=response().choices
        @property
        def usage(self): raise RuntimeError("PRIVATE")
    r=Bad()
    assert asyncio.run(generate_candidate(Client([r]),"fake-model",[],diagnostic_observer=lambda r:None))=="PRIVATE_CONTENT"


def runner():
    spec=importlib.util.spec_from_file_location("generator_diag_cli",ROOT/"tests/run_dev_generator_diagnostic.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_diagnostic_dry_run_zero_credentials_network_artifacts(monkeypatch,capsys):
    m=runner()
    original_get=m.os.environ.get
    def guarded(name,*args):
        if name in {"OPENROUTER_API_KEY","TEST_DIAG_KEY"}:pytest.fail("Credential lookup")
        return original_get(name,*args)
    monkeypatch.setattr(m.os.environ,"get",guarded)
    monkeypatch.setattr(m,"is_dev_runtime",lambda:pytest.fail("Unexpected DEV guard"))
    monkeypatch.setattr(m.coaching_generator,"generate_candidate",lambda *a,**k:pytest.fail("Generator call"))
    assert m.main([])==0
    report=json.loads(capsys.readouterr().out)
    assert report["dry_run"] and report["planned_turns"]==6
    assert report["network_calls"]==report["credential_lookups"]==report["artifact_writes"]==0


def test_diagnostic_live_requires_explicit_settings(capsys):
    assert runner().main(["--live","--scenario-id","work_and_autonomy"])==2


def test_diagnostic_dev_guard_before_credentials(monkeypatch):
    m=runner();monkeypatch.setattr(m,"is_dev_runtime",lambda:False)
    original_get=m.os.environ.get
    def guarded(name,*args):
        if name in {"OPENROUTER_API_KEY","TEST_DIAG_KEY"}:pytest.fail("Credential lookup")
        return original_get(name,*args)
    monkeypatch.setattr(m.os.environ,"get",guarded)
    with pytest.raises(ValueError):asyncio.run(m.diagnose(load_scenarios()[0],BenchmarkConfig(),live=True))


def test_diagnostic_stops_first_failure_no_retry_history_or_raw_output(monkeypatch):
    m=runner();monkeypatch.setattr(m,"is_dev_runtime",lambda:True);monkeypatch.setenv("TEST_DIAG_KEY","SECRET")
    scenario=load_scenarios()[0];client=Client([response(),response("",finish="length",reasoning="PRIVATE_REASONING")])
    r=asyncio.run(m.diagnose(scenario,BenchmarkConfig("fake-model","https://example.invalid/v1","TEST_DIAG_KEY"),live=True,client=client))
    assert not r["completed"] and r["attempt_count"]==2 and r["failed_attempt_count"]==1
    assert len(client.calls)==2 and all(c["max_tokens"]==350 for c in client.calls)
    assert r["signal_counts"]["finish_reason_length"]==1 and r["finish_reason_counts"]["length"]==1
    assert client.calls[1]["messages"][1:]==[{"role":"user","content":scenario["turns"][0]},
        {"role":"assistant","content":"PRIVATE_CONTENT"},{"role":"user","content":scenario["turns"][1]}]
    failed=r["attempts"][-1]
    assert failed["failure_kind"]=="empty_response" and "finish_reason_length" in failed["diagnostic"]["signals"]
    for text in ["PRIVATE_CONTENT","PRIVATE_REASONING","SECRET",*scenario["turns"]]:assert text not in json.dumps(r,ensure_ascii=False)


def test_diagnostic_provider_exception_stops_without_retry(monkeypatch):
    m=runner();monkeypatch.setattr(m,"is_dev_runtime",lambda:True);monkeypatch.setenv("TEST_DIAG_KEY","SECRET")
    client=Client([APIStatusError("PRIVATE_PROVIDER")])
    r=asyncio.run(m.diagnose(load_scenarios()[0],BenchmarkConfig("fake-model","https://example.invalid/v1","TEST_DIAG_KEY"),live=True,client=client))
    assert len(client.calls)==1 and r["attempts"][0]["diagnostic"]["provider_error_category"]=="http_error"


def test_diagnostic_has_no_database_telegram_ports_or_artifact_writes():
    for path in ["services/generator_diagnostics.py","tests/run_dev_generator_diagnostic.py"]:
        source=(ROOT/path).read_text();tree=ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):names=[n.name for n in node.names]
            elif isinstance(node,ast.ImportFrom):names=[node.module or ""]
            else:continue
            assert all(n.split('.')[0] not in {"database","telegram","aiogram","handlers","bot","sqlite3","aiosqlite"} for n in names)
        for port in ["add_chat_message","get_recent_history","clear_chat_history","getUpdates","write_report","mkdir","write_text"]:assert port not in source



def test_live_still_requires_explicit_scenario(capsys):
    assert runner().main(["--live","--model","z-ai/glm-5.2","--base-url","https://openrouter.ai/api/v1","--api-key-env","OPENROUTER_API_KEY"])==2
