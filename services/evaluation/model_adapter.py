"""Replaceable OpenAI-compatible adapter; no network without explicit live=True."""

import json
import math
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Protocol
from urllib import error, request
from urllib.parse import urlsplit


def sanitize(value, secret=None, depth=0):
    """Sanitize persisted diagnostics, including JSON nested inside strings.

    Header/environment containers are dropped, URLs reduced to hosts, and known
    secrets plus recognizable credential strings redacted. This is not a DLP
    detector for arbitrary unknown secrets; callers must supply the active key.
    """
    if depth > 24:
        return "[REDACTED_DEPTH_LIMIT]"
    if isinstance(value, dict):
        result = {}
        sensitive = {"authorization", "proxyauthorization", "headers", "requestheaders",
                     "responseheaders", "apikey", "xapikey", "accesstoken", "refreshtoken",
                     "token", "secret", "password", "credentials", "credential",
                     "environment", "environmentvariables", "env", "environ", "osenviron",
                     "reasoning", "reasoningcontent", "reasoningdetails", "thinking", "thinkingcontent"}
        for key, item in value.items():
            safe_key = sanitize(str(key), secret, depth + 1)
            normalized = re.sub(r"[^a-z0-9]", "", safe_key.lower())
            if normalized not in sensitive and not normalized.endswith("headers"):
                result[safe_key] = sanitize(item, secret, depth + 1)
        return result
    if isinstance(value, list):
        return [sanitize(item, secret, depth + 1) for item in value]
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith(("{", "[", '"')):
        try:
            decoded = json.loads(value)
        except (ValueError, RecursionError):
            pass
        else:
            if isinstance(decoded, (dict, list, str)):
                return json.dumps(sanitize(decoded, secret, depth + 1), ensure_ascii=False)
    # Decode escaped credential text even when the enclosing JSON is malformed.
    text = value
    for _ in range(4):
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
        if decoded == text:
            break
        text = decoded
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?im)(?:proxy-)?authorization\s*[:=]\s*[^\r\n]*", "[REDACTED_HEADER]", text)
    text = re.sub(r"(?i)\bbearer\s+[^\s\"'<>;,}]+", "[REDACTED_TOKEN]", text)
    text = re.sub(r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*[^\s\"';,}]+", "[REDACTED_CREDENTIAL]", text)
    text = re.sub(r"(?im)\b(?:environment(?: variables)?|request[_ -]?headers)\s*[:=][^\r\n]*", "[REDACTED_CONTAINER]", text)
    text = re.sub(r"\b(?!HF[0-9]{2}\b)[A-Z][A-Z0-9_]{2,}\s*=\s*[^\s\"';,}]+", "[REDACTED_ENV]", text)
    def safe_url(match):
        try:
            url = urlsplit(match.group(0))
            host = url.hostname
            if not host or "[REDACTED]" in host:
                return "[REDACTED_URL]"
            return url.scheme + "://" + host + "/[REDACTED_URL_DETAILS]"
        except ValueError:
            return "[REDACTED_URL]"
    return re.sub(r"https?://[^\s<>\"']+", safe_url, text)


ERROR_KINDS = frozenset({
    "timeout", "transport_error", "http_error", "provider_error", "empty_response",
    "response_format_error", "response_too_large", "live_flag_required", "missing_api_key",
    "invalid_model", "invalid_timeout", "invalid_key_environment_name", "invalid_base_url",
    "truncated_response", "invalid_generation_config",
})


class AdapterError(ValueError):
    def __init__(self, kind, raw_response=None, details=None, secret=None):
        self.kind = kind if kind in ERROR_KINDS else "transport_error"
        self.raw_response = sanitize(raw_response, secret)
        self.details = sanitize(details or {}, secret)
        self.details = {key: value[:2000] if isinstance(value, str) else value
                        for key, value in self.details.items()}
        super().__init__(f"Model adapter failure: {self.kind}")


class ModelParseError(ValueError):
    """Malformed evaluator JSON, distinct from contract-invalid JSON objects."""


@dataclass(frozen=True)
class ModelReply:
    text: str
    raw_response: str
    details: dict = field(default_factory=dict)


class EvaluatorModel(Protocol):
    def complete(self, messages, *, live=False) -> ModelReply:
        ...


@dataclass(frozen=True)
class ModelConfig:
    model: str
    base_url: str
    timeout: float = 60.0
    api_key_env: str = "OPENROUTER_API_KEY"
    max_tokens: int | None = 2500
    reasoning: dict | None = None
    reasoning_effort: str | None = None

    def generation_parameters(self):
        """Explicit provider-specific options; absent optional fields are omitted."""
        self.validate()
        parameters = {"temperature": 0}
        if self.max_tokens is not None:
            parameters["max_tokens"] = self.max_tokens
        if self.reasoning is not None:
            # Copy JSON data so requests cannot mutate caller configuration.
            parameters["reasoning"] = json.loads(json.dumps(self.reasoning, allow_nan=False))
        if self.reasoning_effort is not None:
            parameters["reasoning_effort"] = self.reasoning_effort
        return parameters

    def validate(self):
        if not isinstance(self.model, str) or not self.model.strip():
            raise AdapterError("invalid_model")
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)) or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise AdapterError("invalid_timeout")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.api_key_env):
            raise AdapterError("invalid_key_environment_name")
        try:
            url = urlsplit(self.base_url)
            port = url.port
        except (TypeError, ValueError):
            raise AdapterError("invalid_base_url") from None
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise AdapterError("invalid_base_url")
        if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise AdapterError("invalid_base_url")
        if any(char.isspace() for char in self.base_url):
            raise AdapterError("invalid_base_url")
        if self.max_tokens is not None and (type(self.max_tokens) is not int or self.max_tokens <= 0):
            raise AdapterError("invalid_generation_config")
        if self.reasoning is not None and self.reasoning_effort is not None:
            raise AdapterError("invalid_generation_config")
        if self.reasoning_effort is not None and (type(self.reasoning_effort) is not str or self.reasoning_effort not in {"low", "medium", "high", "minimal", "none"}):
            raise AdapterError("invalid_generation_config")
        if self.reasoning is not None:
            if type(self.reasoning) is not dict or not self.reasoning:
                raise AdapterError("invalid_generation_config")
            if "max_tokens" in self.reasoning and (type(self.reasoning["max_tokens"]) is not int or self.reasoning["max_tokens"] <= 0):
                raise AdapterError("invalid_generation_config")
            try:
                json.dumps(self.reasoning, allow_nan=False)
            except (ValueError, TypeError, RecursionError):
                raise AdapterError("invalid_generation_config") from None
        return self


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


MAX_RESPONSE_BYTES = 1024 * 1024


def _provider_error(payload):
    if type(payload) is not dict:
        return None
    for key in ("error", "errors"):
        if key in payload and (payload[key] not in (None, False, [], {}) or "choices" not in payload):
            return payload[key] if payload[key] is not None else payload
    if payload.get("success") is False or payload.get("status") in ("error", "failed", "failure") or payload.get("type") == "error":
        return payload
    return None


def _diagnostics(config, status, provider=None):
    details = {"http_status": status, "model": config.model,
               "backend_host": urlsplit(config.base_url).hostname}
    if isinstance(provider, list):
        provider = provider[0] if provider else None
    if isinstance(provider, str):
        details["message"] = provider
    elif isinstance(provider, dict):
        for key in ("type", "code", "message"):
            value = provider.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                details[key] = value
    return details


def _read_body(response):
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise AdapterError("response_too_large")
    return data.decode("utf-8")


class OpenAICompatibleAdapter:
    def __init__(self, config, transport=None):
        self.config = config.validate()
        # No credential lookup or HTTP request at construction/import time.
        self.transport = transport

    def complete(self, messages, *, live=False):
        if live is not True:
            raise AdapterError("live_flag_required")
        key = os.environ.get(self.config.api_key_env)
        if not key or not key.strip():
            raise AdapterError("missing_api_key")
        parameters = self.config.generation_parameters()
        body = json.dumps({"model": self.config.model, "messages": messages,
                           **parameters}).encode("utf-8")
        req = request.Request(self.config.base_url.rstrip("/") + "/chat/completions", data=body,
                              headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        status = 200
        try:
            transport = self.transport or request.build_opener(_NoRedirect()).open
            with transport(req, timeout=self.config.timeout) as response:
                status = getattr(response, "status", 200)
                raw = _read_body(response)
        except error.HTTPError as exc:
            status = exc.code
            raw = None
            provider = None
            try:
                raw = _read_body(exc)
                payload = json.loads(raw)
                provider = _provider_error(payload)
                if provider is None and isinstance(payload, dict):
                    provider = payload
            except (AdapterError, ValueError, OSError, UnicodeError, RecursionError, AttributeError):
                pass
            finally:
                exc.close()
            raise AdapterError("http_error", raw_response=raw,
                               details=_diagnostics(self.config, status, provider), secret=key) from None
        except AdapterError:
            raise
        except (TimeoutError, socket.timeout):
            raise AdapterError("timeout", details=_diagnostics(self.config, None), secret=key) from None
        except error.URLError as exc:
            kind = "timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "transport_error"
            raise AdapterError(kind, details=_diagnostics(self.config, None), secret=key) from None
        except (OSError, ValueError, UnicodeError):
            raise AdapterError("transport_error", details=_diagnostics(self.config, None), secret=key) from None
        details = _diagnostics(self.config, status)
        if not raw.strip():
            raise AdapterError("empty_response", raw_response=raw, details=details, secret=key)
        try:
            payload = json.loads(raw)
        except (ValueError, RecursionError):
            raise AdapterError("response_format_error", raw_response=raw, details=details, secret=key) from None
        provider = _provider_error(payload)
        if provider is not None:
            raise AdapterError("provider_error", raw_response=raw,
                               details=_diagnostics(self.config, status, provider), secret=key)
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            text = message["content"]
        except (KeyError, IndexError, TypeError):
            raise AdapterError("response_format_error", raw_response=raw, details=details, secret=key) from None
        details["finish_reason"] = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None
        native = choice.get("native_finish_reason", payload.get("native_finish_reason"))
        if isinstance(native, str):
            details["native_finish_reason"] = native
        if isinstance(payload.get("provider"), str):
            details["provider"] = payload["provider"]
        details["reasoning_present"] = any(
            bool(value.strip()) if isinstance(value, str) else bool(value)
            for name in ("reasoning", "reasoning_content", "reasoning_details")
            for value in [message.get(name)])
        if text is None or isinstance(text, str) and not text.strip():
            kind = "truncated_response" if details["finish_reason"] == "length" else "empty_response"
            raise AdapterError(kind, raw_response=raw, details=details, secret=key)
        if not isinstance(text, str):
            raise AdapterError("response_format_error", raw_response=raw, details=details, secret=key)
        # Evaluator text is parsed unchanged; debug envelopes are sanitized now.
        return ModelReply(text=text, raw_response=sanitize(raw, key), details=sanitize(details, key))


def parse_model_json(raw):
    """Accept one JSON object or one entire JSON fence; never extract from prose."""
    if not isinstance(raw, str):
        raise ModelParseError("Model output must be a string")
    text = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ModelParseError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ModelParseError("Nonstandard JSON constant")

    try:
        result = json.loads(text, object_pairs_hook=unique, parse_constant=invalid)
    except (ValueError, RecursionError):
        raise ModelParseError("Malformed evaluator JSON") from None
    if type(result) is not dict:
        raise ModelParseError("Evaluator JSON must be an object")
    return result
