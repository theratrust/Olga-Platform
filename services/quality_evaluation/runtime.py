"""DEV-only observational quality evaluation; no qualification or routing authority."""
import asyncio
import copy
import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from services.evaluation.runtime import is_dev_runtime
from .contract import QualityContractError, validate_result
from .model_adapter import AdapterError, ModelConfig, ModelParseError, OpenAICompatibleAdapter, parse_model_json, sanitize
from .prompt import QualityPromptBuilder
from .repair import contract_diagnostic, retry_eligible, retry_messages

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = True
LOG_FIELDS = frozenset({"event", "timestamp", "mode", "evaluator_model", "candidate_hash", "session_hash",
    "scores", "quality_flags", "overall_quality", "insufficient_context", "first_pass_contract_valid",
    "retry_attempted", "retry_recovered", "final_contract_valid", "latency_ms",
    "evaluator_error_kind", "first_pass_error_kind"})


@dataclass(frozen=True)
class QualityShadowConfig:
    enabled: bool = False
    model: str = "z-ai/glm-5.2"
    max_tokens: int = 4000
    reasoning_effort: str = "low"
    timeout: float = 60.0
    base_url: str = "https://openrouter.ai/api/v1"

    @classmethod
    def from_env(cls):
        if os.environ.get("QUALITY_EVALUATOR_SHADOW_ENABLED", "false").strip().lower() != "true":
            return cls()
        return cls(True, os.environ.get("QUALITY_EVALUATOR_MODEL", "z-ai/glm-5.2"),
                   int(os.environ.get("QUALITY_EVALUATOR_MAX_TOKENS", "4000")),
                   os.environ.get("QUALITY_EVALUATOR_REASONING_EFFORT", "low"),
                   float(os.environ.get("QUALITY_EVALUATOR_TIMEOUT_SECONDS", "60")),
                   os.environ.get("QUALITY_EVALUATOR_BASE_URL", "https://openrouter.ai/api/v1"))

    def adapter_config(self):
        return ModelConfig(self.model, self.base_url, self.timeout, "OPENROUTER_API_KEY",
                           self.max_tokens, reasoning_effort=self.reasoning_effort).validate()


def _emit(record, secret=None):
    try:
        safe = sanitize({k: v for k, v in record.items() if k in LOG_FIELDS}, secret)
        LOGGER.info("%s %s", safe["event"], json.dumps(safe, ensure_ascii=False, allow_nan=False))
    except Exception:
        pass


def _attempt(messages, evaluator_input, adapter):
    attempt = {"contract_valid": False, "result": None, "error": None}
    try:
        reply = adapter.complete(messages, live=True)
        parsed = parse_model_json(reply.text)
        attempt["result"] = validate_result(parsed, evaluator_input)
        attempt["contract_valid"] = True
    except AdapterError as exc:
        attempt["error"] = {"kind": exc.kind}
    except ModelParseError:
        attempt["error"] = {"kind": "malformed_json"}
    except QualityContractError as exc:
        attempt["error"] = {"kind": "contract_invalid_output", **contract_diagnostic(exc)}
    except Exception:
        attempt["error"] = {"kind": "unexpected_exception"}
    return attempt


def evaluate_candidate_quality_shadow(conversation_context, user_message, candidate_response,
                                      *, config=None, adapter=None, builder=None, session_id=None):
    """Blocking worker observation. Return aggregates only, never an actionable result."""
    started = time.perf_counter()
    secret = None
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "quality_shadow",
              "event": "QUALITY_SHADOW_EVAL_FAIL", "evaluator_model": "z-ai/glm-5.2",
              "candidate_hash": None, "session_hash": None, "scores": None, "quality_flags": [],
              "overall_quality": None, "insufficient_context": None,
              "first_pass_contract_valid": False, "retry_attempted": False,
              "retry_recovered": False, "final_contract_valid": False,
              "latency_ms": 0, "evaluator_error_kind": None, "first_pass_error_kind": None}
    try:
        config = config or QualityShadowConfig.from_env()
        if not config.enabled:
            return None
        if not is_dev_runtime():
            record["evaluator_error_kind"] = "dev_identity_rejected"
        else:
            model_config = config.adapter_config()
            secret = os.environ.get("OPENROUTER_API_KEY")
            record["evaluator_model"] = config.model
            record["candidate_hash"] = hashlib.sha256(candidate_response.encode("utf-8")).hexdigest()
            record["session_hash"] = hashlib.sha256(str(session_id).encode("utf-8")).hexdigest() if session_id is not None else None
            evaluator_input = {"conversation_context": copy.deepcopy(conversation_context[-20:]),
                               "user_message": user_message, "candidate_response": candidate_response}
            messages = (builder or QualityPromptBuilder()).build(evaluator_input)
            adapter = adapter if adapter is not None else OpenAICompatibleAdapter(model_config)
            first = _attempt(messages, evaluator_input, adapter)
            record["first_pass_contract_valid"] = first["contract_valid"]
            record["first_pass_error_kind"] = first["error"]["kind"] if first["error"] else None
            final = first
            if retry_eligible(first):
                record["retry_attempted"] = True
                final = _attempt(retry_messages(messages, first["error"]), evaluator_input, adapter)
            record["final_contract_valid"] = final["contract_valid"]
            record["retry_recovered"] = record["retry_attempted"] and final["contract_valid"]
            if final["contract_valid"]:
                result = final["result"]
                record.update(event="QUALITY_SHADOW_EVAL_RECOVERED" if record["retry_recovered"] else "QUALITY_SHADOW_EVAL_OK",
                              scores=result["scores"], quality_flags=[f["flag_id"] for f in result["quality_flags"]],
                              overall_quality=result["overall_quality"], insufficient_context=result["insufficient_context"]["present"])
            else:
                record["evaluator_error_kind"] = final["error"]["kind"]
    except AdapterError as exc:
        record["evaluator_error_kind"] = exc.kind
    except Exception:
        record["evaluator_error_kind"] = "configuration_or_runtime_error"
    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    safe = sanitize(record, secret)
    _emit(safe)
    return {"log": safe}


class QualityShadowDispatcher:
    """Independent single worker; one outstanding observation, no queued backlog."""
    def __init__(self, config=None, evaluator=evaluate_candidate_quality_shadow):
        self.config = config
        self.evaluator = evaluator
        self.tasks = set()
        self.inflight = set()
        self.executor = None
        self.closed = False
        self.disabled = False

    def submit(self, conversation_context, user_message, candidate_response, *, session_id=None):
        try:
            config = self.config or QualityShadowConfig.from_env()
            if not config.enabled or self.closed or self.disabled:
                return False
            if not is_dev_runtime():
                self._fail("dev_identity_rejected")
                return False
            config.adapter_config()
            if self.tasks or self.inflight:
                self._fail("capacity_exceeded")
                return False
            loop = asyncio.get_running_loop()
            context = copy.deepcopy(conversation_context[-20:])
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="olga-quality-shadow")
            async def observe():
                try:
                    future = loop.run_in_executor(self.executor, lambda: self.evaluator(
                        context, user_message, candidate_response, config=config, session_id=session_id))
                    self.inflight.add(future)
                    future.add_done_callback(self._worker_done)
                    # Cancelling the coroutine cannot release the active worker slot.
                    await asyncio.shield(future)
                except Exception:
                    self._fail("background_exception")
            task = loop.create_task(observe())
            self.tasks.add(task)
            task.add_done_callback(self._done)
            _emit({"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "quality_shadow",
                   "event": "QUALITY_SHADOW_EVAL_SCHEDULED", "evaluator_model": config.model,
                   "candidate_hash": hashlib.sha256(candidate_response.encode("utf-8")).hexdigest(),
                   "session_hash": hashlib.sha256(str(session_id).encode("utf-8")).hexdigest() if session_id is not None else None},
                  os.environ.get("OPENROUTER_API_KEY"))
            return True
        except Exception:
            self._fail("configuration_or_scheduling_error")
            return False

    @staticmethod
    def _fail(kind):
        _emit({"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "quality_shadow",
               "event": "QUALITY_SHADOW_EVAL_FAIL", "evaluator_error_kind": kind})

    def disable(self):
        self.disabled = True

    def _done(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _worker_done(self, future):
        self.inflight.discard(future)
        if not future.cancelled():
            future.exception()

    async def close(self):
        self.closed = True
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        if self.inflight:
            await asyncio.gather(*tuple(self.inflight), return_exceptions=True)
        if self.executor is not None:
            self.executor.shutdown(wait=False)
