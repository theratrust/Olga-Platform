"""Offline quality-shadow tests with synthetic runtime inputs and fake ports."""
import asyncio
import ast
import copy
import hashlib
import importlib.util
import json
import socket
import sys
import threading
import types
from pathlib import Path
from unittest.mock import AsyncMock
from urllib import request
import pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.quality_evaluation import runtime
from services.quality_evaluation.contract import DIMENSIONS
from services.quality_evaluation.model_adapter import AdapterError, ModelReply
from services.evaluation.runtime import ShadowDispatcher

CANDIDATE = "Что тебе самой сейчас важно?"
USER = "Я не знаю."
CONTEXT = [{"role": "assistant", "content": "Что сейчас важно?"}, {"role": "user", "content": USER}]
CONFIG = runtime.QualityShadowConfig(enabled=True)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Live calls forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(request.OpenerDirector, "open", forbidden)
    monkeypatch.delenv("QUALITY_EVALUATOR_SHADOW_ENABLED", raising=False)
    monkeypatch.delenv("EVALUATOR_SHADOW_ENABLED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "SYNTHETIC_QUALITY_SECRET")


def result(flag=False):
    value = {"scores": dict.fromkeys(DIMENSIONS, 2), "quality_flags": [],
             "overall_quality": "strong", "reason": "PRIVATE_RATIONALE",
             "insufficient_context": {"present": False, "items": []}}
    if flag:
        value["scores"]["naturalness"] = 1
        value["overall_quality"] = "acceptable"
        value["quality_flags"] = [{"flag_id": "Q06_TEMPLATE_LANGUAGE", "evidence": CANDIDATE}]
    return value


class Model:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
    def complete(self, messages, *, live=False):
        assert live is True
        self.calls.append(copy.deepcopy(messages))
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return ModelReply(output if isinstance(output, str) else json.dumps(output),
                          "PRIVATE_PROVIDER_ENVELOPE SYNTHETIC_QUALITY_SECRET",
                          {"reasoning": "PRIVATE_REASONING"})


def run(outputs, **kwargs):
    model = Model(outputs)
    record = runtime.evaluate_candidate_quality_shadow(CONTEXT, USER, CANDIDATE,
        config=CONFIG, adapter=model, session_id="PRIVATE_SESSION", **kwargs)
    return record, model


def test_disabled_default_zero_calls_and_credentials(monkeypatch, caplog):
    original = runtime.os.environ.get
    def guarded(name, *args):
        assert name != "OPENROUTER_API_KEY"
        return original(name, *args)
    monkeypatch.setattr(runtime.os.environ, "get", guarded)
    model = Model([])
    assert not runtime.QualityShadowConfig.from_env().enabled
    assert runtime.evaluate_candidate_quality_shadow(CONTEXT, USER, CANDIDATE, adapter=model) is None
    async def scenario():
        dispatcher = runtime.QualityShadowDispatcher()
        assert not dispatcher.submit(CONTEXT, USER, CANDIDATE)
        assert dispatcher.executor is None
        await dispatcher.close()
    asyncio.run(scenario())
    assert not model.calls
    assert not [r for r in caplog.records if r.name == runtime.__name__]


@pytest.mark.parametrize("value", ["false", "1", "yes", "on", ""])
def test_only_explicit_true_enables_quality(value, monkeypatch):
    monkeypatch.setenv("QUALITY_EVALUATOR_SHADOW_ENABLED", value)
    assert not runtime.QualityShadowConfig.from_env().enabled


def test_methodology_namespace_does_not_enable_quality(monkeypatch):
    monkeypatch.setenv("EVALUATOR_SHADOW_ENABLED", "true")
    model = Model([])
    assert runtime.evaluate_candidate_quality_shadow(CONTEXT, USER, CANDIDATE, adapter=model) is None
    assert not model.calls


def test_quality_env_enables_with_exact_defaults(monkeypatch):
    monkeypatch.setenv("QUALITY_EVALUATOR_SHADOW_ENABLED", "true")
    config = runtime.QualityShadowConfig.from_env()
    assert config.enabled and config.model == "z-ai/glm-5.2"
    assert (config.max_tokens, config.reasoning_effort, config.timeout) == (4000, "low", 60)
    adapter_config = config.adapter_config()
    assert adapter_config.api_key_env == "OPENROUTER_API_KEY"
    assert adapter_config.base_url == "https://openrouter.ai/api/v1"
    assert adapter_config.generation_parameters() == {"temperature": 0, "max_tokens": 4000, "reasoning_effort": "low"}
    model = Model([result()])
    record = runtime.evaluate_candidate_quality_shadow(CONTEXT, USER, CANDIDATE, adapter=model)
    assert record["log"]["final_contract_valid"] and len(model.calls) == 1


@pytest.mark.parametrize("flag", [False, True])
def test_valid_logs_safe_aggregates_only(flag, caplog):
    original = copy.deepcopy(CONTEXT)
    record, model = run([result(flag)])
    log = record["log"]
    assert log["event"] == "QUALITY_SHADOW_EVAL_OK"
    assert log["mode"] == "quality_shadow"
    assert log["scores"] == result(flag)["scores"]
    assert log["quality_flags"] == (["Q06_TEMPLATE_LANGUAGE"] if flag else [])
    assert log["overall_quality"] == result(flag)["overall_quality"]
    assert log["insufficient_context"] is False
    assert log["candidate_hash"] == hashlib.sha256(CANDIDATE.encode()).hexdigest()
    assert log["session_hash"] == hashlib.sha256(b"PRIVATE_SESSION").hexdigest()
    assert log["first_pass_contract_valid"] and log["final_contract_valid"]
    assert not log["retry_attempted"] and not log["retry_recovered"]
    assert set(record) == {"log"} and set(log) <= runtime.LOG_FIELDS
    assert CONTEXT == original and len(model.calls) == 1
    text = caplog.text + json.dumps(record, ensure_ascii=False)
    for private in (CANDIDATE, USER, CONTEXT[0]["content"], "PRIVATE_SESSION", "PRIVATE_RATIONALE",
                    "PRIVATE_PROVIDER_ENVELOPE", "PRIVATE_REASONING", "SYNTHETIC_QUALITY_SECRET"):
        assert private not in text


@pytest.mark.parametrize("kind", ["timeout", "provider_error", "http_error", "transport_error"])
def test_provider_failures_fail_open_no_retry(kind, caplog):
    record, model = run([AdapterError(kind, raw_response="PRIVATE_PROVIDER_ENVELOPE")])
    assert record["log"]["event"] == "QUALITY_SHADOW_EVAL_FAIL"
    assert record["log"]["evaluator_error_kind"] == kind
    assert not record["log"]["retry_attempted"] and len(model.calls) == 1
    assert "PRIVATE_PROVIDER_ENVELOPE" not in caplog.text


@pytest.mark.parametrize("failure", ["malformed", "empty", "truncated", "structure"])
@pytest.mark.parametrize("recover", [False, True])
def test_structural_retry_at_most_two(failure, recover):
    invalid = result()
    del invalid["scores"]
    first = {"malformed": "broken", "empty": AdapterError("empty_response"),
             "truncated": AdapterError("truncated_response"), "structure": invalid}[failure]
    record, model = run([first, result() if recover else first, result()])
    log = record["log"]
    assert len(model.calls) == 2
    assert not log["first_pass_contract_valid"] and log["retry_attempted"]
    assert log["retry_recovered"] == log["final_contract_valid"] == recover
    assert log["event"] == ("QUALITY_SHADOW_EVAL_RECOVERED" if recover else "QUALITY_SHADOW_EVAL_FAIL")
    repair = model.calls[1][-1]["content"]
    assert "Исправь только формат и структуру." in repair
    for value in ("PRIVATE_RATIONALE", "overall_quality", "Q06_TEMPLATE_LANGUAGE", "strong", "acceptable"):
        assert value not in repair


@pytest.mark.parametrize("mutation", ["evidence", "score", "flag", "overall"])
def test_semantic_contract_errors_not_retried(mutation):
    value = result(True)
    if mutation == "evidence":
        value["quality_flags"][0]["evidence"] = "not in supplied conversation"
    elif mutation == "score":
        value["scores"]["naturalness"] = 9
    elif mutation == "flag":
        value["quality_flags"][0]["flag_id"] = "Q99_UNKNOWN"
    else:
        value["overall_quality"] = "strong"
    record, model = run([value])
    assert len(model.calls) == 1 and not record["log"]["retry_attempted"]
    assert record["log"]["evaluator_error_kind"] == "contract_invalid_output"


def test_bounded_history_preserves_last_twenty_ordered_messages():
    history = [{"role": "user" if i % 2 else "assistant", "content": str(i)} for i in range(25)]
    original = copy.deepcopy(history)
    model = Model([result()])
    runtime.evaluate_candidate_quality_shadow(history, USER, CANDIDATE, config=CONFIG, adapter=model)
    payload = json.loads(model.calls[0][1]["content"].split("\n", 1)[1])
    assert payload["conversation_context"] == history[-20:]
    assert history == original


def test_dev_guard_rejection_prevents_provider_and_credentials(monkeypatch):
    monkeypatch.setattr(runtime, "is_dev_runtime", lambda: False)
    original = runtime.os.environ.get
    def guarded(name, *args):
        assert name != "OPENROUTER_API_KEY"
        return original(name, *args)
    monkeypatch.setattr(runtime.os.environ, "get", guarded)
    record, model = run([])
    assert not model.calls and record["log"]["evaluator_error_kind"] == "dev_identity_rejected"
    async def scenario():
        manager = runtime.QualityShadowDispatcher(CONFIG, lambda *a, **k: pytest.fail("provider called"))
        assert not manager.submit(CONTEXT, USER, CANDIDATE)
        assert manager.executor is None
        await manager.close()
    asyncio.run(scenario())


def test_runtime_no_gold_metrics_qualification_dependency():
    source = (ROOT / "services/quality_evaluation/runtime.py").read_text()
    imports = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)]
    assert not any(node.module in ("qualification", "metrics") for node in imports)
    for forbidden in ("load_corpus", "validate_case", "response_quality_evaluator_cases", "compare_results", "calculate_metrics", "quality_gold_result"):
        assert forbidden not in source
    guard = [node for node in imports if node.module == "services.evaluation.runtime"]
    assert len(guard) == 1 and [name.name for name in guard[0].names] == ["is_dev_runtime"]


async def entered_worker(entered):
    for _ in range(500):
        if entered.is_set():
            return
        await asyncio.sleep(.001)
    pytest.fail("worker did not start")


@pytest.mark.parametrize("cancel", [False, True])
def test_dispatcher_nonblocking_one_worker_saturation_and_shutdown(cancel, caplog):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def worker(*a, **k):
        calls.append(True)
        entered.set()
        assert release.wait(3)
    async def scenario():
        manager = runtime.QualityShadowDispatcher(CONFIG, worker)
        assert manager.submit(CONTEXT, USER, CANDIDATE)
        assert not manager.submit(CONTEXT, USER, CANDIDATE)
        await entered_worker(entered)
        assert manager.executor._max_workers == 1
        if cancel:
            task = next(iter(manager.tasks))
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            assert manager.inflight
        assert not manager.submit(CONTEXT, USER, CANDIDATE)
        closer = asyncio.create_task(manager.close())
        await asyncio.sleep(.01)
        assert not closer.done()
        assert not manager.submit(CONTEXT, USER, CANDIDATE)
        release.set()
        await closer
        assert not manager.tasks and not manager.inflight
    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert calls == [True] and "capacity_exceeded" in caplog.text


def test_disable_prevents_new_observations():
    async def scenario():
        manager = runtime.QualityShadowDispatcher(CONFIG, lambda *a, **k: pytest.fail("called"))
        manager.disable()
        assert not manager.submit(CONTEXT, USER, CANDIDATE)
        assert manager.executor is None
        await manager.close()
    asyncio.run(scenario())


def test_dynamic_env_disable(monkeypatch):
    calls = []
    async def scenario():
        manager = runtime.QualityShadowDispatcher(evaluator=lambda *a, **k: calls.append(True))
        monkeypatch.setenv("QUALITY_EVALUATOR_SHADOW_ENABLED", "true")
        assert manager.submit(CONTEXT, USER, CANDIDATE)
        while manager.tasks:
            await asyncio.sleep(.001)
        monkeypatch.setenv("QUALITY_EVALUATOR_SHADOW_ENABLED", "false")
        assert not manager.submit(CONTEXT, USER, CANDIDATE)
        await manager.close()
    asyncio.run(scenario())
    assert calls == [True]


def test_independent_methodology_and_quality_capacity():
    entered_a, entered_b, release = threading.Event(), threading.Event(), threading.Event()
    def worker(entered):
        def observe(*a, **k):
            entered.set()
            assert release.wait(3)
        return observe
    async def scenario():
        from services.evaluation.runtime import ShadowConfig
        method = ShadowDispatcher(ShadowConfig(enabled=True), worker(entered_a))
        quality = runtime.QualityShadowDispatcher(CONFIG, worker(entered_b))
        assert method.submit(CONTEXT, USER, CANDIDATE)
        await entered_worker(entered_a)
        assert quality.submit(CONTEXT, USER, CANDIDATE)
        await entered_worker(entered_b)
        assert method.executor is not quality.executor
        release.set()
        await asyncio.gather(method.close(), quality.close())
    try:
        asyncio.run(scenario())
    finally:
        release.set()


@pytest.mark.parametrize("status", ["ok", "recovered", "fail"])
def test_one_scheduled_and_final_event(status, caplog):
    outputs = {"ok": [result()], "recovered": ["broken", result()], "fail": [AdapterError("timeout")]}
    model = Model(outputs[status])
    def worker(*a, **k):
        return runtime.evaluate_candidate_quality_shadow(*a, adapter=model, **k)
    async def scenario():
        manager = runtime.QualityShadowDispatcher(CONFIG, worker)
        assert manager.submit(CONTEXT, USER, CANDIDATE, session_id="PRIVATE_SESSION")
        await manager.close()
    asyncio.run(scenario())
    logs = [json.loads(r.getMessage().split(" ", 1)[1]) for r in caplog.records if r.name == runtime.__name__]
    assert [r["event"] for r in logs] == ["QUALITY_SHADOW_EVAL_SCHEDULED", {
        "ok": "QUALITY_SHADOW_EVAL_OK", "recovered": "QUALITY_SHADOW_EVAL_RECOVERED", "fail": "QUALITY_SHADOW_EVAL_FAIL"}[status]]
    assert all(set(r) <= runtime.LOG_FIELDS for r in logs)
    for private in (CANDIDATE, USER, "PRIVATE_SESSION", "PRIVATE_RATIONALE", "PRIVATE_PROVIDER_ENVELOPE", "SYNTHETIC_QUALITY_SECRET"):
        assert private not in caplog.text


def test_missing_credential_fail_open(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    record = runtime.evaluate_candidate_quality_shadow(CONTEXT, USER, CANDIDATE, config=CONFIG)
    assert record["log"]["evaluator_error_kind"] == "missing_api_key"
    assert not record["log"]["retry_attempted"]


def test_unexpected_error_and_logging_failure_contained(monkeypatch, caplog):
    record, model = run([RuntimeError("Authorization: Bearer SYNTHETIC_QUALITY_SECRET")])
    assert record["log"]["evaluator_error_kind"] == "unexpected_exception"
    assert "Authorization" not in caplog.text and "SYNTHETIC_QUALITY_SECRET" not in caplog.text
    def broken(*a, **k):
        raise RuntimeError("logging unavailable")
    monkeypatch.setattr(runtime.LOGGER, "info", broken)
    record, model = run([result()])
    assert record["log"]["final_contract_valid"]


def chat_module(monkeypatch):
    spec = importlib.util.spec_from_file_location("method_shadow_test_ports", ROOT / "tests/test_evaluator_shadow_runtime.py")
    ports = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ports)
    return ports.load_chat_handler(monkeypatch)


@pytest.mark.parametrize("direct", [True, False])
@pytest.mark.parametrize("method_fails", [True, False])
@pytest.mark.parametrize("logging_fails", [True, False])
def test_delivery_before_quality_failure_preserves_candidate(monkeypatch, direct, method_fails, logging_fails, caplog):
    module = chat_module(monkeypatch)
    if logging_fails:
        original_error = module.logging.error
        def log_error(message, *args, **kwargs):
            if message.startswith("QUALITY_SHADOW_EVAL_FAIL"):
                raise RuntimeError("QUALITY_PRIVATE_LOG_EXCEPTION")
            return original_error(message, *args, **kwargs)
        monkeypatch.setattr(module.logging, "error", log_error)
    async def scenario(quality_enabled):
        deliveries, observations = [], []
        async def send(user_id, text, **kwargs):
            deliveries.append((user_id, text, kwargs))
        bot = types.SimpleNamespace(send_chat_action=AsyncMock(), send_message=send)
        class Registrar:
            def __call__(self, *a): return lambda function: function
            def register(self, *a): pass
        dp = types.SimpleNamespace(message=Registrar())
        response = types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=CANDIDATE))])
        generate = AsyncMock(return_value=response)
        client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=generate)))
        async def recent(*a, **k): return copy.deepcopy(CONTEXT)
        def method(*a, **k):
            assert deliveries
            observations.append("method")
            if method_fails:
                raise RuntimeError("method hook failure")
        def quality(context, user, candidate, **kwargs):
            assert deliveries and observations == ["method"]
            assert candidate == CANDIDATE and user == USER and context == CONTEXT
            observations.append("quality")
            raise RuntimeError("QUALITY_PRIVATE_EXCEPTION")
        pending = AsyncMock(return_value=55)
        handler = module.register_chat(dp, bot, client, "existing-coach", [99],
            types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")), lambda u: "Тест", lambda u: "Тест",
            AsyncMock(), recent, pending, AsyncMock(), direct_chat=direct, shadow_observer=method,
            quality_shadow_observer=quality if quality_enabled else None)
        state = types.SimpleNamespace(get_state=AsyncMock(return_value="chat"), get_data=AsyncMock(return_value={}))
        message = types.SimpleNamespace(from_user=types.SimpleNamespace(id=12, username=None), text=USER,
                                        chat=types.SimpleNamespace(id=12), answer=AsyncMock())
        await handler(message, state)
        assert generate.await_count == 1 and message.answer.await_count == 1
        assert generate.call_args.kwargs["max_tokens"] == 350
        assert observations == (["method", "quality"] if quality_enabled else ["method"])
        return deliveries, pending.call_args
    assert asyncio.run(scenario(False)) == asyncio.run(scenario(True))
    assert "QUALITY_PRIVATE_EXCEPTION" not in caplog.text
    assert "QUALITY_PRIVATE_LOG_EXCEPTION" not in caplog.text
    if not logging_fails:
        logs = [json.loads(r.getMessage().split(" ", 1)[1]) for r in caplog.records
                if r.getMessage().startswith("QUALITY_SHADOW_EVAL_FAIL ")]
        assert len(logs) == 1
        assert set(logs[0]) <= runtime.LOG_FIELDS
        assert logs[0]["evaluator_error_kind"] == "post_delivery_hook_error"


def test_bot_wiring_and_shutdown_keeps_direct_chat():
    source = (ROOT / "bot.py").read_text()
    assert "quality_shadow_dispatcher = QualityShadowDispatcher()" in source
    assert "quality_shadow_observer=quality_shadow_dispatcher.submit" in source
    assert "await quality_shadow_dispatcher.close()" in source
    assert "direct_chat=DEV_DIRECT_CHAT" in source
