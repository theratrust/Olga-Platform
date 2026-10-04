"""DEV-only observational evaluation; no gold corpus, regeneration or route execution."""

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
from pathlib import Path

from .contract import PROJECT_ROOT, ContractError, validate_result
from .model_adapter import AdapterError, ModelConfig, ModelParseError, OpenAICompatibleAdapter, parse_model_json, sanitize
from .prompt import EvaluatorPromptBuilder
from .repair import contract_diagnostic, retry_eligible, retry_messages

LOGGER = logging.getLogger(__name__)
DEV_ROOT = Path("/opt/olga-coaching-dev")


def is_dev_runtime(project_root=None, *, environ=None, mountinfo_path=None):
    """Fail closed using module location plus existing DEV container provenance.

    /app alone, DEV_DIRECT_CHAT alone, or a configurable boolean is not identity.
    This reads no env file, Docker socket, database or provider endpoint.
    """
    env = os.environ if environ is None else environ
    try:
        root = Path(PROJECT_ROOT if project_root is None else project_root).resolve()
        if root not in (DEV_ROOT, Path("/app")):
            return False
        # Explicit contradictory environment declarations override path evidence.
        for key in ("APP_ENV", "ENVIRONMENT", "BOT_ENV", "RUNTIME_ENV"):
            if key in env and env[key].strip().lower() not in {"dev", "development"}:
                return False
        if "ENV_FILE" in env and env["ENV_FILE"] not in {
                ".env.dev", "/app/.env.dev", "/opt/olga-coaching-dev/.env.dev"}:
            return False
        if "DB_NAME" in env and env["DB_NAME"] != "dev_bot.db":
            return False
        if root == DEV_ROOT:
            return True
        if env.get("DB_NAME") != "dev_bot.db":
            return False
        path = Path("/proc/self/mountinfo") if mountinfo_path is None else Path(mountinfo_path)
        app_mounts = []
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 10 or "-" not in fields:
                return False
            if fields[4] == "/app":
                app_mounts.append(fields)
        return len(app_mounts) == 1 and app_mounts[0][3] == str(DEV_ROOT)
    except (OSError, ValueError, RuntimeError, TypeError, AttributeError):
        return False


@dataclass(frozen=True)
class ShadowConfig:
    enabled: bool = False
    model: str = "z-ai/glm-5.2"
    max_tokens: int = 4000
    reasoning_effort: str = "low"
    timeout: float = 60.0
    base_url: str = "https://openrouter.ai/api/v1"

    @classmethod
    def from_env(cls):
        if os.environ.get("EVALUATOR_SHADOW_ENABLED", "false").strip().lower() != "true":
            return cls()
        return cls(True, os.environ.get("EVALUATOR_MODEL", "z-ai/glm-5.2"),
                   int(os.environ.get("EVALUATOR_MAX_TOKENS", "4000")),
                   os.environ.get("EVALUATOR_REASONING_EFFORT", "low"),
                   float(os.environ.get("EVALUATOR_TIMEOUT_SECONDS", "60")),
                   os.environ.get("EVALUATOR_BASE_URL", "https://openrouter.ai/api/v1"))

    def adapter_config(self):
        return ModelConfig(self.model, self.base_url, self.timeout, "OPENROUTER_API_KEY",
                           self.max_tokens, {"effort": self.reasoning_effort}).validate()


def _attempt(messages, candidate, adapter, secret):
    parsed = None
    attempt = {"contract_valid": False, "result": None, "error": None}
    try:
        reply = adapter.complete(messages, live=True)
        parsed = parse_model_json(reply.text)
        attempt["result"] = validate_result(parsed, candidate)
        attempt["contract_valid"] = True
    except AdapterError as exc:
        attempt["error"] = {"category": "adapter", "kind": exc.kind}
    except ModelParseError:
        attempt["error"] = {"category": "parse", "kind": "malformed_model_json"}
    except ContractError as exc:
        attempt["error"] = {"category": "contract", "kind": "contract_invalid_result",
                            **contract_diagnostic(exc, parsed, secret)}
    except Exception:
        attempt["error"] = {"category": "runtime", "kind": "unexpected_exception"}
    # Provider envelopes, partial content and reasoning are never persisted here.
    return attempt


def _emit(record):
    try:
        LOGGER.info("%s %s", record["event"], json.dumps(record, ensure_ascii=False, allow_nan=False))
    except Exception:
        # Observability itself must not fail the user interaction.
        pass


def evaluate_candidate_shadow(conversation_context, user_message, candidate_response,
                              *, config=None, adapter=None, builder=None, session_id=None):
    """Blocking worker boundary; callers schedule after delivery, never await it to send."""
    started = time.perf_counter()
    secret = os.environ.get("OPENROUTER_API_KEY")
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "shadow",
              "event": "SHADOW_EVAL_FAIL", "evaluator_model": "z-ai/glm-5.2",
              "candidate_hash": None, "session_hash": None, "hard_fail": None,
              "violations": [], "scores": None, "overall": None, "decision": None,
              "shadow_route": None, "insufficient_context": None,
              "first_pass_contract_valid": False, "retry_attempted": False,
              "retry_recovered": False, "final_contract_valid": False,
              "latency_ms": 0, "evaluator_error_kind": None, "first_pass_error_kind": None}
    attempts = []
    result = None
    try:
        config = config or ShadowConfig.from_env()
        if not config.enabled:
            return None
        if not is_dev_runtime():
            raise ValueError("DEV-only evaluator")
        record["evaluator_model"] = config.model
        record["candidate_hash"] = hashlib.sha256(candidate_response.encode("utf-8")).hexdigest()
        if session_id is not None:
            record["session_hash"] = hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()
        model_config = config.adapter_config()
        if adapter is None:
            adapter = OpenAICompatibleAdapter(model_config)
        builder = builder or EvaluatorPromptBuilder()
        # Only the generator's supplied ordered, already bounded history is used.
        messages = builder.build({"conversation_context": copy.deepcopy(conversation_context[-20:]),
                                  "user_message": user_message, "candidate_response": candidate_response})
        first = _attempt(messages, candidate_response, adapter, secret)
        attempts.append(first)
        record["first_pass_contract_valid"] = first["contract_valid"]
        record["first_pass_error_kind"] = first["error"]["kind"] if first["error"] else None
        if retry_eligible(first):
            record["retry_attempted"] = True
            attempts.append(_attempt(retry_messages(messages, first["error"]), candidate_response, adapter, secret))
        final = attempts[-1]
        result = final["result"]
        record["final_contract_valid"] = final["contract_valid"]
        record["retry_recovered"] = record["retry_attempted"] and final["contract_valid"]
        if result is not None:
            record.update(event="SHADOW_EVAL_RECOVERED" if record["retry_recovered"] else "SHADOW_EVAL_OK",
                          hard_fail=result["hard_fail"], violations=[v["rule_id"] for v in result["violations"]],
                          scores=result["scores"], overall=result["overall"], decision=result["decision"],
                          shadow_route=result["decision"], insufficient_context=result["insufficient_context"]["present"])
        else:
            record["evaluator_error_kind"] = final["error"]["kind"]
    except Exception:
        record["evaluator_error_kind"] = "unexpected_exception"
    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    safe = sanitize(record, secret)
    _emit(safe)
    # Result is for observation only. Logging excludes rationale/excerpts and raw inputs.
    return {"log": safe, "result": sanitize(result, secret), "attempts": sanitize(attempts, secret)}


class ShadowDispatcher:
    """One worker and at most one in-flight task; saturation drops observations."""
    def __init__(self, config=None, evaluator=evaluate_candidate_shadow):
        self.config = config
        self.evaluator = evaluator
        self.tasks = set()
        self.inflight = set()
        self.executor = None
        self.closed = False
        self.disabled = False

    def submit(self, conversation_context, user_message, candidate_response, *, session_id=None):
        """Non-awaiting post-delivery hook; errors are contained and consume no user time."""
        try:
            config = self.config or ShadowConfig.from_env()
            if not config.enabled or self.closed or self.disabled:
                return False
            if self.tasks or self.inflight:
                _emit({"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "shadow",
                       "event": "SHADOW_EVAL_FAIL", "evaluator_error_kind": "capacity_exceeded"})
                return False
            loop = asyncio.get_running_loop()
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="olga-shadow")
            context = copy.deepcopy(conversation_context[-20:])
            async def observe():
                try:
                    future = loop.run_in_executor(self.executor, lambda: self.evaluator(
                        context, user_message, candidate_response, config=config, session_id=session_id))
                    self.inflight.add(future)
                    future.add_done_callback(self._worker_done)
                    # Cancellation of the observer must not release an active worker slot.
                    await asyncio.shield(future)
                except Exception:
                    _emit({"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "shadow",
                           "event": "SHADOW_EVAL_FAIL", "evaluator_error_kind": "background_exception"})
            task = loop.create_task(observe())
            self.tasks.add(task)
            task.add_done_callback(self._done)
            return True
        except Exception:
            _emit({"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "shadow",
                   "event": "SHADOW_EVAL_FAIL", "evaluator_error_kind": "configuration_or_scheduling_error"})
            return False

    def disable(self):
        """Immediately stop new observations; active worker remains bounded and drains."""
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
