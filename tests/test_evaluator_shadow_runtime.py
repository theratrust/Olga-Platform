"""Offline shadow tests: synthetic conversations, fake providers and Telegram ports."""

import asyncio
import copy
import importlib.util
import json
import logging
import subprocess
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
from services.evaluation import runtime
from services.evaluation.model_adapter import AdapterError, ModelReply

CANDIDATE = "Что тебе самой сейчас важно?\nС чем хочется остаться? 🌺"
CONTEXT = [{"role": "assistant", "content": "Что сейчас важно?"},
           {"role": "user", "content": "Я не знаю."}]
CONFIG = runtime.ShadowConfig(enabled=True)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("No live calls in shadow tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(request.OpenerDirector, "open", forbidden)
    monkeypatch.delenv("EVALUATOR_SHADOW_ENABLED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "SYNTHETIC_SHADOW_KEY")


def mock_result(decision="accept"):
    result = {"hard_fail": False, "violations": [], "scores": {
        "client_authorship": 2, "grounding": 2, "hypothesis_freedom": 2, "respectful_style": 2},
        "overall": "pass", "decision": "accept", "reason": "Сохранено авторство клиента.",
        "source_refs": [{"path": "knowledge/method/метод_Ольги.md",
                         "section": "Не давать готовых решений", "provenance": "direct_olga_confirmed"}],
        "insufficient_context": {"present": False, "items": []}}
    if decision in ("retry", "escalate"):
        result.update(hard_fail=True, overall="fail", decision=decision)
        result["violations"] = [{"rule_id": "HF01" if decision == "retry" else "HF05",
                                 "excerpt": "Что тебе самой сейчас важно?", "reason": "Тестовое нарушение.",
                                 "source_refs": copy.deepcopy(result["source_refs"])}]
        result["scores"]["client_authorship"] = 0
    elif decision == "insufficient_context":
        result.update(overall="insufficient_context", decision=decision)
        result["scores"]["grounding"] = None
        result["insufficient_context"] = {"present": True, "items": [
            {"rule_ids": ["HF08"], "missing": "Предыдущая гипотеза.", "reason": "Нет предыдущего хода."}]}
    return result


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
        return ModelReply(output, "PROVIDER_RAW_NOT_FOR_LOGS")


def run_model(outputs, **kwargs):
    model = Model(outputs)
    record = runtime.evaluate_candidate_shadow(CONTEXT, "Я не знаю.", CANDIDATE,
        config=CONFIG, adapter=model, session_id=12345, **kwargs)
    return record, model


def test_shadow_disabled_by_default_and_no_dispatch():
    model = Model([])
    assert runtime.ShadowConfig.from_env().enabled is False
    assert runtime.evaluate_candidate_shadow(CONTEXT, "Я не знаю.", CANDIDATE, adapter=model) is None
    assert model.calls == []
    assert CANDIDATE == "Что тебе самой сейчас важно?\nС чем хочется остаться? 🌺"


@pytest.mark.parametrize("decision", ["accept", "retry", "escalate", "insufficient_context"])
def test_decisions_are_logged_only_without_regeneration(decision, caplog):
    caplog.set_level("INFO", logger=runtime.__name__)
    original = copy.deepcopy(CONTEXT)
    record, model = run_model([json.dumps(mock_result(decision))])
    assert len(model.calls) == 1
    assert CONTEXT == original
    assert record["log"]["event"] == "SHADOW_EVAL_OK"
    assert record["log"]["shadow_route"] == decision
    assert record["log"]["decision"] == decision
    assert record["log"]["final_contract_valid"]
    assert decision in caplog.text and "SHADOW_EVAL_OK" in caplog.text
    assert CANDIDATE not in caplog.text and "Я не знаю." not in caplog.text
    assert "12345" not in caplog.text
    for forbidden in ("EXACT_MATCH", "SEMANTIC_MISMATCH", "DETAIL_VARIANCE", "TAXONOMY_VARIANCE"):
        assert forbidden not in caplog.text


@pytest.mark.parametrize("kind", ["timeout", "provider_error", "http_error", "transport_error"])
def test_provider_failures_fail_open_without_retry(kind):
    record, model = run_model([AdapterError(kind)])
    assert len(model.calls) == 1
    assert record["log"]["event"] == "SHADOW_EVAL_FAIL"
    assert record["log"]["evaluator_error_kind"] == kind
    assert record["log"]["shadow_route"] is None


@pytest.mark.parametrize("failure", ["malformed", "structure", "truncated", "empty"])
def test_structural_repair_reuses_policy_once_and_preserves_first_failure(failure):
    invalid = mock_result()
    del invalid["scores"]
    outputs = {"malformed": "broken", "structure": json.dumps(invalid),
               "truncated": AdapterError("truncated_response"), "empty": AdapterError("empty_response")}
    record, model = run_model([outputs[failure], json.dumps(mock_result())])
    assert len(model.calls) == len(record["attempts"]) == 2
    assert not record["log"]["first_pass_contract_valid"]
    assert record["log"]["retry_attempted"] and record["log"]["retry_recovered"]
    assert record["log"]["event"] == "SHADOW_EVAL_RECOVERED"
    assert "Исправь только формат и структуру." in model.calls[1][-1]["content"]
    assert record["log"]["shadow_route"] == "accept"


def test_unrecovered_malformed_output_fails_open_maximum_two_attempts():
    record, model = run_model(["broken", "broken", json.dumps(mock_result())])
    assert len(model.calls) == 2
    assert record["log"]["event"] == "SHADOW_EVAL_FAIL"
    assert record["log"]["evaluator_error_kind"] == "malformed_model_json"


def test_priority_error_has_no_semantic_retry():
    invalid = mock_result()
    invalid["decision"] = "retry"
    record, model = run_model([json.dumps(invalid)])
    assert len(model.calls) == 1
    assert record["attempts"][0]["error"]["contract_error_kind"] == "decision_priority_error"
    assert record["log"]["event"] == "SHADOW_EVAL_FAIL"


def test_unexpected_exception_and_secrets_fail_open(caplog):
    caplog.set_level("INFO", logger=runtime.__name__)
    record, model = run_model([RuntimeError("Authorization: Bearer SYNTHETIC_SHADOW_KEY ENV_SECRET=private")])
    assert record["log"]["evaluator_error_kind"] == "unexpected_exception"
    assert "SYNTHETIC_SHADOW_KEY" not in caplog.text + json.dumps(record)
    assert "ENV_SECRET" not in caplog.text and "Authorization" not in caplog.text


def test_raw_provider_and_rationale_are_not_logged(caplog):
    caplog.set_level("INFO", logger=runtime.__name__)
    result = mock_result()
    result["reason"] = "Authorization: Bearer SYNTHETIC_SHADOW_KEY"
    record, _ = run_model([json.dumps(result)])
    assert "SYNTHETIC_SHADOW_KEY" not in json.dumps(record) + caplog.text
    assert "PROVIDER_RAW_NOT_FOR_LOGS" not in json.dumps(record) + caplog.text
    assert "Authorization" not in caplog.text


def test_bounded_history_preserves_roles_and_order():
    history = [{"role": "user" if i % 2 else "assistant", "content": str(i)} for i in range(25)]
    model = Model([json.dumps(mock_result())])
    runtime.evaluate_candidate_shadow(history, "Я не знаю.", CANDIDATE, config=CONFIG, adapter=model)
    envelope = json.loads(model.calls[0][1]["content"].split("\n", 1)[1])
    assert envelope["conversation_context"] == history[-20:]


def test_configuration_defaults_and_explicit_false(monkeypatch):
    config = runtime.ShadowConfig.from_env()
    assert not config.enabled and config.model == "z-ai/glm-5.2"
    assert config.max_tokens == 4000 and config.reasoning_effort == "low" and config.timeout == 60
    monkeypatch.setenv("EVALUATOR_SHADOW_ENABLED", "true")
    enabled = runtime.ShadowConfig.from_env()
    assert enabled.enabled
    assert enabled.adapter_config().reasoning == {"effort": "low"}
    monkeypatch.setenv("EVALUATOR_SHADOW_ENABLED", "false")
    assert not runtime.ShadowConfig.from_env().enabled


def test_runtime_has_no_gold_qualification_or_corpus_dependencies():
    source = (ROOT / "services/evaluation/runtime.py").read_text()
    policy = (ROOT / "services/evaluation/repair.py").read_text()
    for forbidden in ("expected_result", "coaching_evaluator_cases", "compare_results", "calculate_metrics", "from .qualification"):
        assert forbidden not in source + policy


def test_non_dev_root_never_calls_evaluator(monkeypatch):
    monkeypatch.setattr(runtime, "PROJECT_ROOT", Path("/synthetic-not-dev"))
    record, model = run_model([])
    assert model.calls == [] and record["log"]["event"] == "SHADOW_EVAL_FAIL"


def test_background_is_nonblocking_bounded_and_consumes_exceptions(caplog):
    caplog.set_level("INFO", logger=runtime.__name__)
    entered = threading.Event()
    release = threading.Event()
    def worker(*a, **k):
        entered.set()
        assert release.wait(2)
        raise RuntimeError("SECRET_BACKGROUND_EXCEPTION")
    async def scenario():
        manager = runtime.ShadowDispatcher(CONFIG, worker)
        assert manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(.001)
        assert entered.is_set() and len(manager.tasks) == 1
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        release.set()
        await manager.close()
        assert not manager.tasks and not manager.inflight
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
    asyncio.run(scenario())
    assert "capacity_exceeded" in caplog.text and "background_exception" in caplog.text
    assert "SECRET_BACKGROUND_EXCEPTION" not in caplog.text


def test_cancelled_observer_does_not_release_worker_capacity():
    entered = threading.Event()
    release = threading.Event()
    def worker(*a, **k):
        entered.set()
        assert release.wait(2)
    async def scenario():
        manager = runtime.ShadowDispatcher(CONFIG, worker)
        manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(.001)
        task = next(iter(manager.tasks))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert manager.inflight
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        release.set()
        await manager.close()
    asyncio.run(scenario())


def test_disabled_dispatcher_has_no_worker():
    async def scenario():
        manager = runtime.ShadowDispatcher(runtime.ShadowConfig())
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        assert manager.executor is None and not manager.tasks
        await manager.close()
    asyncio.run(scenario())


def load_chat_handler(monkeypatch):
    # aiogram is absent on the host; stub only its registration/type ports.
    class Expression:
        def __getattr__(self, name): return self
        def startswith(self, *a): return self
        def __invert__(self): return self
        def __and__(self, other): return self
    modules = {
        "aiogram": {"Bot": object, "Dispatcher": object, "F": Expression(),
                    "types": types.SimpleNamespace(Message=object)},
        "aiogram.filters": {"Command": lambda *a: object()},
        "aiogram.fsm.context": {"FSMContext": object},
        "aiogram.types": {"InlineKeyboardButton": lambda **k: k, "InlineKeyboardMarkup": lambda **k: k},
    }
    for name, attributes in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("shadow_test_chat", ROOT / "handlers/chat.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("observer_kind", ["disabled", "accept", "retry", "escalate", "insufficient_context", "timeout", "provider", "unexpected"])
def test_actual_chat_handler_delivers_identical_candidate_before_observation(monkeypatch, observer_kind):
    module = load_chat_handler(monkeypatch)
    delivered = []
    calls = []
    async def send(user_id, text, **kwargs):
        delivered.append(text)
    bot = types.SimpleNamespace(send_chat_action=AsyncMock(), send_message=send)
    class Registrar:
        def __call__(self, *a): return lambda function: function
        def register(self, *a): pass
    dp = types.SimpleNamespace(message=Registrar())
    response = types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=CANDIDATE))])
    generate = AsyncMock(return_value=response)
    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=generate)))
    history = copy.deepcopy(CONTEXT)
    async def recent(*a, **k):
        assert k == {"limit": 20}
        return history
    def observe(context, user, candidate, **kwargs):
        assert delivered == [CANDIDATE]
        assert context == history and candidate == CANDIDATE
        calls.append(candidate)
        if observer_kind == "unexpected":
            raise RuntimeError("not user-visible")
        if observer_kind == "disabled":
            manager = runtime.ShadowDispatcher(runtime.ShadowConfig())
            assert not manager.submit(context, user, candidate)
        else:
            output = AdapterError("timeout" if observer_kind == "timeout" else "provider_error") if observer_kind in ("timeout", "provider") else json.dumps(mock_result(observer_kind))
            runtime.evaluate_candidate_shadow(context, user, candidate, config=CONFIG, adapter=Model([output]))
    handler = module.register_chat(dp, bot, client, "existing-coach", [],
        types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")), lambda u: "Тест", lambda u: "Тест",
        AsyncMock(), recent, AsyncMock(), AsyncMock(), direct_chat=True, shadow_observer=observe)
    state = types.SimpleNamespace(get_state=AsyncMock(return_value="chat"), get_data=AsyncMock(return_value={}), update_data=AsyncMock())
    message = types.SimpleNamespace(from_user=types.SimpleNamespace(id=12, username=None), text="Я не знаю.",
                                    chat=types.SimpleNamespace(id=12), answer=AsyncMock())
    asyncio.run(handler(message, state))
    assert delivered == calls == [CANDIDATE]
    assert delivered[0].encode("utf-8") == CANDIDATE.encode("utf-8")
    assert generate.await_count == 1
    assert generate.call_args.kwargs["max_tokens"] == 350
    assert message.answer.await_count == 1  # Existing acknowledgement only; no evaluator error message.


def test_missing_credential_is_fail_open_before_transport(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    record = runtime.evaluate_candidate_shadow(CONTEXT, "Я не знаю.", CANDIDATE, config=CONFIG)
    assert record["log"]["evaluator_error_kind"] == "missing_api_key"
    assert record["log"]["event"] == "SHADOW_EVAL_FAIL"
    assert not record["log"]["retry_attempted"]


def test_prompt_builder_exception_is_fail_open_without_dispatch():
    class BrokenBuilder:
        def build(self, *a):
            raise RuntimeError("SECRET_PROMPT_FAILURE")
    model = Model([])
    record = runtime.evaluate_candidate_shadow(CONTEXT, "Я не знаю.", CANDIDATE,
        config=CONFIG, builder=BrokenBuilder(), adapter=model)
    assert model.calls == []
    assert record["log"]["evaluator_error_kind"] == "unexpected_exception"
    assert "SECRET_PROMPT_FAILURE" not in json.dumps(record)


def test_logging_failure_does_not_escape(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("logging unavailable")
    monkeypatch.setattr(runtime.LOGGER, "info", broken)
    record, model = run_model([json.dumps(mock_result())])
    assert record["log"]["final_contract_valid"] and len(model.calls) == 1


def test_recovered_logs_preserve_first_failure_and_redact_both_attempts(caplog):
    caplog.set_level("INFO", logger=runtime.__name__)
    invalid = mock_result()
    del invalid["scores"]
    invalid["reason"] = "Authorization: Bearer SYNTHETIC_SHADOW_KEY"
    result = mock_result()
    result["reason"] = "Authorization: Bearer SYNTHETIC_SHADOW_KEY"
    record, model = run_model([json.dumps(invalid), json.dumps(result)])
    assert len(model.calls) == 2
    assert record["log"]["first_pass_error_kind"] == "contract_invalid_result"
    assert record["log"]["event"] == "SHADOW_EVAL_RECOVERED"
    assert "SYNTHETIC_SHADOW_KEY" not in json.dumps(record) + caplog.text + json.dumps(model.calls)
    assert "Authorization" not in caplog.text


def test_dynamic_disable_prevents_new_work(monkeypatch):
    calls = []
    def worker(*a, **k):
        calls.append(True)
    async def scenario():
        manager = runtime.ShadowDispatcher(evaluator=worker)
        monkeypatch.setenv("EVALUATOR_SHADOW_ENABLED", "true")
        assert manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        while manager.tasks:
            await asyncio.sleep(.001)
        monkeypatch.setenv("EVALUATOR_SHADOW_ENABLED", "false")
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        await manager.close()
    asyncio.run(scenario())
    assert calls == [True]


def test_moderation_delivery_unchanged_and_hook_runs_after_admin_delivery(monkeypatch):
    module = load_chat_handler(monkeypatch)
    async def run(observer_enabled):
        deliveries = []
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
        def observe(*a, **k):
            assert deliveries and deliveries[0][0] == 99
            raise RuntimeError("safe hook failure")
        pending = AsyncMock(return_value=55)
        handler = module.register_chat(dp, bot, client, "existing-coach", [99],
            types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")), lambda u: "Тест", lambda u: "Тест",
            AsyncMock(), recent, pending, AsyncMock(), direct_chat=False,
            shadow_observer=observe if observer_enabled else None)
        message = types.SimpleNamespace(from_user=types.SimpleNamespace(id=12, username=None), text="Я не знаю.",
                                        chat=types.SimpleNamespace(id=12), answer=AsyncMock())
        state = types.SimpleNamespace(get_state=AsyncMock(return_value="chat"), get_data=AsyncMock(return_value={}), update_data=AsyncMock())
        await handler(message, state)
        assert generate.await_count == pending.await_count == message.answer.await_count == 1
        return deliveries, pending.call_args
    baseline = asyncio.run(run(False))
    shadow = asyncio.run(run(True))
    assert shadow == baseline


def test_immediate_in_process_disable_prevents_dispatch():
    calls = []
    manager = runtime.ShadowDispatcher(CONFIG, lambda *a, **k: calls.append(True))
    manager.disable()
    async def scenario():
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        assert manager.executor is None
        await manager.close()
    asyncio.run(scenario())
    assert calls == []


@pytest.fixture
def dev_mountinfo(tmp_path):
    path = tmp_path / "mountinfo"
    path.write_text("123 1 8:1 /opt/olga-coaching-dev /app rw,relatime - ext4 /dev/sda1 rw\n")
    return path


def test_guard_host_dev_accepted_without_cwd_dependence(monkeypatch):
    monkeypatch.chdir(ROOT / "tests")
    assert runtime.is_dev_runtime(ROOT, environ={})


def test_guard_dev_container_app_accepted_with_existing_markers(dev_mountinfo):
    assert runtime.is_dev_runtime("/app", environ={"DB_NAME": "dev_bot.db", "DEV_DIRECT_CHAT": "true"},
                                  mountinfo_path=dev_mountinfo)


@pytest.mark.parametrize("env", [{}, {"DEV_DIRECT_CHAT": "true"}, {"APP_ENV": "dev"}])
def test_guard_app_without_required_dev_markers_rejected(dev_mountinfo, env):
    assert not runtime.is_dev_runtime("/app", environ=env, mountinfo_path=dev_mountinfo)


@pytest.mark.parametrize("root", ["/opt/olga-coaching-bot", "/tmp/arbitrary-runtime"])
def test_guard_prod_and_arbitrary_roots_rejected(dev_mountinfo, root):
    assert not runtime.is_dev_runtime(root, environ={"DB_NAME": "dev_bot.db", "DEV_DIRECT_CHAT": "true"},
                                      mountinfo_path=dev_mountinfo)


@pytest.mark.parametrize("mount", [
    "123 1 8:1 /opt/olga-coaching-bot /app rw - ext4 /dev/sda1 rw\n",
    "123 1 8:1 / /app rw - overlay overlay rw\n",
    "", "malformed\n",
    "123 1 8:1 /opt/olga-coaching-dev /app rw - ext4 /dev/sda1 rw\n" * 2,
])
def test_guard_app_requires_unambiguous_dev_mount_provenance(tmp_path, mount):
    path = tmp_path / "mountinfo"
    path.write_text(mount)
    assert not runtime.is_dev_runtime("/app", environ={"DB_NAME": "dev_bot.db"}, mountinfo_path=path)


@pytest.mark.parametrize("env", [
    {"DB_NAME": "dev_bot.db", "APP_ENV": "production"},
    {"DB_NAME": "dev_bot.db", "ENVIRONMENT": "staging"},
    {"DB_NAME": "dev_bot.db", "ENV_FILE": ".env.prod"},
    {"DB_NAME": "prod_bot.db", "DEV_DIRECT_CHAT": "true"},
])
def test_guard_contradictory_markers_rejected(dev_mountinfo, env):
    for root in ("/app", str(ROOT)):
        assert not runtime.is_dev_runtime(root, environ=env, mountinfo_path=dev_mountinfo)


def test_guard_unreadable_mount_evidence_fails_closed(tmp_path):
    assert not runtime.is_dev_runtime("/app", environ={"DB_NAME": "dev_bot.db"},
                                      mountinfo_path=tmp_path / "missing-mountinfo")


def test_container_guard_integrates_without_changing_fail_open(monkeypatch, dev_mountinfo):
    original = runtime.is_dev_runtime
    monkeypatch.setattr(runtime, "is_dev_runtime", lambda: original("/app", environ={"DB_NAME": "dev_bot.db"}, mountinfo_path=dev_mountinfo))
    record, model = run_model([AdapterError("timeout")])
    assert len(model.calls) == 1
    assert record["log"]["event"] == "SHADOW_EVAL_FAIL"
    assert record["log"]["evaluator_error_kind"] == "timeout"


def test_runtime_info_logging_overrides_only_its_own_inherited_warning(monkeypatch, caplog):
    root = logging.getLogger()
    monkeypatch.setattr(root, "level", logging.WARNING)
    assert runtime.LOGGER.getEffectiveLevel() == logging.INFO
    assert runtime.LOGGER.isEnabledFor(logging.INFO)
    assert runtime.LOGGER.propagate is True
    root_handlers = list(root.handlers)
    runtime_handlers = list(runtime.LOGGER.handlers)
    run_model([json.dumps(mock_result())])
    records = [record for record in caplog.records if record.name == runtime.__name__]
    assert len(records) == 1 and records[0].getMessage().startswith("SHADOW_EVAL_OK ")
    assert root.level == logging.WARNING
    assert root.handlers == root_handlers and runtime.LOGGER.handlers == runtime_handlers


@pytest.mark.parametrize("status", ["ok", "recovered", "fail"])
def test_one_scheduled_event_and_one_final_event_without_sensitive_text(caplog, status):
    outputs = {"ok": [json.dumps(mock_result())],
               "recovered": ["broken", json.dumps(mock_result())],
               "fail": [AdapterError("timeout")]}
    model = Model(outputs[status])
    def worker(context, user, candidate, **kwargs):
        return runtime.evaluate_candidate_shadow(context, user, candidate, adapter=model, **kwargs)
    async def scenario():
        manager = runtime.ShadowDispatcher(CONFIG, worker)
        assert manager.submit(CONTEXT, "Я не знаю.", CANDIDATE, session_id="PRIVATE_SESSION_ID")
        await manager.close()
    asyncio.run(scenario())
    records = [record for record in caplog.records if record.name == runtime.__name__]
    events = [json.loads(record.getMessage().split(" ", 1)[1]) for record in records]
    expected_final = {"ok": "SHADOW_EVAL_OK", "recovered": "SHADOW_EVAL_RECOVERED", "fail": "SHADOW_EVAL_FAIL"}[status]
    assert [event["event"] for event in events] == ["SHADOW_EVAL_SCHEDULED", expected_final]
    scheduled = events[0]
    assert scheduled["mode"] == "shadow" and scheduled["evaluator_model"] == "z-ai/glm-5.2"
    assert len(scheduled["candidate_hash"]) == len(scheduled["session_hash"]) == 64
    for secret in (CANDIDATE, "Я не знаю.", "PRIVATE_SESSION_ID", "SYNTHETIC_SHADOW_KEY", "PROVIDER_RAW_NOT_FOR_LOGS"):
        assert secret not in caplog.text


def test_disabled_shadow_emits_no_scheduling_or_evaluation_records(caplog):
    model = Model([])
    async def scenario():
        manager = runtime.ShadowDispatcher(runtime.ShadowConfig(), lambda *a, **k: pytest.fail("No evaluator call"))
        assert not manager.submit(CONTEXT, "Я не знаю.", CANDIDATE)
        await manager.close()
    asyncio.run(scenario())
    assert runtime.evaluate_candidate_shadow(CONTEXT, "Я не знаю.", CANDIDATE,
                                            config=runtime.ShadowConfig(), adapter=model) is None
    assert model.calls == []
    assert not [record for record in caplog.records if record.name == runtime.__name__]


def test_repeated_import_does_not_duplicate_stream_output_or_change_root_policy():
    # Isolated logging setup mirrors an existing Docker stderr handler; no bot import.
    code = """
import importlib, io, logging
stream = io.StringIO()
root = logging.getLogger()
root.setLevel(logging.WARNING)
handler = logging.StreamHandler(stream)
root.addHandler(handler)
from services.evaluation import runtime
importlib.reload(runtime)
importlib.reload(runtime)
assert root.level == logging.WARNING
assert root.handlers == [handler]
assert not runtime.LOGGER.handlers
assert runtime.LOGGER.propagate
runtime._emit({"event": "SHADOW_EVAL_OK", "mode": "shadow"})
assert len(stream.getvalue().splitlines()) == 1
assert stream.getvalue().startswith("SHADOW_EVAL_OK ")
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
