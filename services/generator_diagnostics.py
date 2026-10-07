"""Opt-in scalar generator-boundary metadata; never serialize provider objects."""
import math

_MISSING = object()
_FINISH = {"stop", "length", "tool_calls", "content_filter", "function_call"}


def _get(obj, name):
    return obj.get(name, _MISSING) if type(obj) is dict else getattr(obj, name, _MISSING)


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _length(value):
    if type(value) is str:
        return len(value)
    if type(value) is list:
        lengths = [_length(_get(v, "text")) for v in value]
        return sum(n for n in lengths if n is not None) if any(n is not None for n in lengths) else None
    return None


def _type(value):
    if value is _MISSING: return "missing"
    # Never emit arbitrary class names supplied by a provider/test object.
    return {str:"str", type(None):"NoneType", list:"list", dict:"dict", int:"int",
            bool:"bool", float:"float", tuple:"tuple"}.get(type(value), "other")


def diagnostic_metadata(response, requested_model, call_succeeded, error, latency_ms):
    choices = _get(response, "choices")
    count = len(choices) if type(choices) in (list, tuple) else None
    choice = choices[0] if count else _MISSING
    message = _get(choice, "message")
    content = _get(message, "content")
    finish = _get(choice, "finish_reason")
    finish = finish if type(finish) is str and finish in _FINISH else "other" if finish is not _MISSING and finish is not None else None
    reasoning = {name: {"present": (value := _get(message, name)) is not _MISSING and value is not None,
                         "character_length": _length(value)}
                 for name in ("reasoning", "reasoning_content", "reasoning_details")}
    tools = _get(message, "tool_calls")
    usage = _get(response, "usage")
    details = _get(usage, "completion_tokens_details")
    model = _get(response, "model")
    matches = type(model) is str and model == requested_model
    # A different provider-controlled string could contain a secret or raw data.
    # Persist only the known request identifier or a fixed mismatch marker.
    safe_model = requested_model if matches else "other_model" if model is not _MISSING and model is not None else None
    status = _get(error, "status_code")
    http_status = status if type(status) is int and 100 <= status <= 599 else None
    category = None
    if error is not None:
        name = type(error).__name__
        category = ("response_shape_error" if call_succeeded else
                    "timeout" if isinstance(error, TimeoutError) or name == "APITimeoutError" else
                    "transport_error" if name == "APIConnectionError" else
                    "http_error" if http_status is not None else "provider_error")
    signals = []
    if not call_succeeded: signals.append("provider_call_failed")
    else:
        if count == 0: signals.append("zero_choices")
        if count is None or type(response) is dict or message is _MISSING or type(message) is dict or content is _MISSING:
            signals.append("unexpected_response_shape")
        if count and content is None: signals.append("content_null")
        if type(content) is str and content == "": signals.append("content_empty_string")
        elif type(content) is str and not content.strip(): signals.append("content_whitespace_only")
        if content is not _MISSING and content is not None and type(content) is not str:
            signals.append("unexpected_content_type")
        if finish == "length": signals.append("finish_reason_length")
        if any(r["present"] for r in reasoning.values()) and (content is _MISSING or content is None or type(content) is str and not content.strip()):
            signals.append("reasoning_without_final_content")
    return {"provider_call_succeeded": call_succeeded is True,
            "choices_count": count, "selected_choice_index": 0 if count else None,
            "finish_reason": finish, "content_present": content is not _MISSING,
            "content_type": _type(content), "content_character_length": len(content) if type(content) is str else None,
            "content_whitespace_only": not content.strip() if type(content) is str else None,
            "reasoning_fields": reasoning,
            "refusal_present": (refusal := _get(message,"refusal")) is not _MISSING and refusal is not None,
            "tool_calls_present": tools is not _MISSING and tools is not None,
            "tool_calls_count": len(tools) if type(tools) in (list, tuple) else None,
            "usage": {**{f:_count(_get(usage,f)) for f in ("prompt_tokens","completion_tokens","total_tokens")},
                      "reasoning_tokens": _count(_get(details,"reasoning_tokens"))},
            "response_model": safe_model, "response_model_matches_request": matches,
            "provider_error_category": category, "http_status": http_status,
            "latency_ms": round(latency_ms,3) if type(latency_ms) in (int,float) and math.isfinite(latency_ms) else None,
            "signals": signals}


def emit_diagnostic(observer, response, requested_model, call_succeeded, error, latency_ms):
    try:
        observer(diagnostic_metadata(response, requested_model, call_succeeded, error, latency_ms))
    except Exception:
        # Metadata access or observer failure must never replace a result/exception.
        pass
