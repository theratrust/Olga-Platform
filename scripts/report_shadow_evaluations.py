"""Aggregate DEV shadow log evidence offline; no bot imports, sockets or subprocesses."""

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

EVENTS = ("SHADOW_EVAL_SCHEDULED", "SHADOW_EVAL_OK", "SHADOW_EVAL_RECOVERED", "SHADOW_EVAL_FAIL")
ROUTES = ("accept", "retry", "escalate", "insufficient_context")
RULES = tuple(f"HF{i:02d}" for i in range(1, 9))
SCORES = ("client_authorship", "grounding", "hypothesis_freedom", "respectful_style")
ERROR_KINDS = frozenset({
    "timeout", "transport_error", "http_error", "provider_error", "empty_response",
    "response_format_error", "response_too_large", "live_flag_required", "missing_api_key",
    "invalid_model", "invalid_timeout", "invalid_key_environment_name", "invalid_base_url",
    "truncated_response", "invalid_generation_config", "malformed_model_json", "contract_invalid_result",
    "unexpected_exception", "capacity_exceeded", "background_exception", "configuration_or_scheduling_error",
})
NON_EVALUATION_FAILURES = frozenset({"capacity_exceeded", "configuration_or_scheduling_error"})
MARKER = re.compile(r"\b(SHADOW_EVAL_SCHEDULED|SHADOW_EVAL_OK|SHADOW_EVAL_RECOVERED|SHADOW_EVAL_FAIL)\s+(\{.*)$")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonstandard JSON constant")


def parse_event(line):
    """Project only safe enums/numbers/flags; never return untrusted text or payloads."""
    try:
        match = MARKER.search(line)
        data = json.loads(match.group(2) if match else line,
                          object_pairs_hook=_unique, parse_constant=_invalid_constant)
        if type(data) is not dict or data.get("mode") != "shadow" or data.get("event") not in EVENTS:
            return None
        if match and match.group(1) != data["event"]:
            return None
        timestamp = data.get("timestamp")
        if not isinstance(timestamp, str):
            return None
        parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed_time.tzinfo is None:
            return None
        hashes = []
        for key in ("candidate_hash", "session_hash"):
            value = data.get(key)
            hashes.append(value.lower() if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) else None)
        # Identity is never exported. Missing hashes fall back to event/time.
        identity = json.dumps([data["event"], parsed_time.timestamp(), *hashes])
        result = {"event": data["event"], "identity": hashlib.sha256(identity.encode()).hexdigest()}
        for key in ("first_pass_contract_valid", "retry_attempted", "retry_recovered", "final_contract_valid", "hard_fail"):
            result[key] = data.get(key) if type(data.get(key)) is bool else None
        result["shadow_route"] = data.get("shadow_route") if data.get("shadow_route") in ROUTES else None
        result["violations"] = sorted({rule for rule in data.get("violations", []) if isinstance(rule, str) and rule in RULES}) if type(data.get("violations")) is list else []
        scores = data.get("scores")
        result["scores"] = {key: scores[key] for key in SCORES if key in scores
                            and (scores[key] is None or type(scores[key]) is int and scores[key] in (0, 1, 2))} if type(scores) is dict else {}
        latency = data.get("latency_ms")
        result["latency_ms"] = latency if type(latency) in (int, float) and math.isfinite(latency) and latency >= 0 else None
        error = data.get("evaluator_error_kind")
        result["evaluator_error_kind"] = error if isinstance(error, str) and error in ERROR_KINDS else "other_error" if error is not None else None
        return result
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize(lines):
    seen = set()
    events = []
    ignored = duplicates = 0
    for line in lines:
        event = parse_event(line)
        if event is None:
            ignored += 1
        elif event["identity"] in seen:
            duplicates += 1
        else:
            seen.add(event["identity"])
            events.append(event)
    scheduled = sum(event["event"] == "SHADOW_EVAL_SCHEDULED" for event in events)
    terminal = [event for event in events if event["event"] != "SHADOW_EVAL_SCHEDULED"
                and event["evaluator_error_kind"] not in NON_EVALUATION_FAILURES]
    counts = {name: sum(event["event"] == "SHADOW_EVAL_" + name.upper() for event in terminal)
              for name in ("ok", "recovered", "fail")}
    valid = [event for event in terminal if event["final_contract_valid"] is True]
    routes = {route: {"count": sum(event["shadow_route"] == route for event in valid),
                      "rate": _rate(sum(event["shadow_route"] == route for event in valid), len(valid))}
              for route in ROUTES}
    hard_known = [event for event in valid if event["hard_fail"] is not None]
    hard_fails = sum(event["hard_fail"] is True for event in hard_known)
    hf = {rule: sum(rule in event["violations"] for event in valid) for rule in RULES}
    distributions = {key: {str(value).lower() if value is not None else "null":
                          sum(key in event["scores"] and event["scores"][key] == value for event in valid)
                          for value in (0, 1, 2, None)} for key in SCORES}
    first_known = [event for event in terminal if event["first_pass_contract_valid"] is not None]
    retry_known = [event for event in terminal if event["retry_attempted"] is not None]
    retried = [event for event in retry_known if event["retry_attempted"]]
    recovery_known = [event for event in retried if event["retry_recovered"] is not None]
    recovered = sum(event["retry_recovered"] is True for event in recovery_known)
    final_known = [event for event in terminal if event["final_contract_valid"] is not None]
    errors = {}
    for event in events:
        if event["evaluator_error_kind"] is not None:
            key = event["evaluator_error_kind"]
            errors[key] = errors.get(key, 0) + 1
    latency = sorted(event["latency_ms"] for event in terminal if event["latency_ms"] is not None)
    return {
        "total_scheduled_evaluations": scheduled, "completed_evaluations": len(terminal),
        "ok_count": counts["ok"], "recovered_count": counts["recovered"], "failed_count": counts["fail"],
        "completion_rate": _rate(len(terminal), scheduled),
        "non_evaluation_failure_events": len(events) - scheduled - len(terminal),
        "duplicate_events_ignored": duplicates, "unrelated_or_malformed_lines_ignored": ignored,
        "routing": {"denominator_final_valid": len(valid), "routes": routes},
        "methodology": {"hard_fail_count": hard_fails, "hard_fail_rate": _rate(hard_fails, len(hard_known)),
                        "hard_fail_known_cases": len(hard_known), "hf_frequency": hf, "score_distribution": distributions},
        "reliability": {
            "first_pass_contract_valid_rate": _rate(sum(event["first_pass_contract_valid"] for event in first_known), len(first_known)),
            "first_pass_known_cases": len(first_known), "retry_attempted_count": len(retried),
            "retry_attempted_rate": _rate(len(retried), len(retry_known)), "retry_attempted_known_cases": len(retry_known),
            "retry_recovered_count": recovered, "retry_recovered_rate": _rate(recovered, len(recovery_known)),
            "retry_recovery_known_cases": len(recovery_known),
            "final_contract_valid_rate": _rate(sum(event["final_contract_valid"] for event in final_known), len(final_known)),
            "final_valid_known_cases": len(final_known), "evaluator_error_kind_frequencies": dict(sorted(errors.items()))},
        "latency_ms": {"count": len(latency), "mean": statistics.mean(latency) if latency else None,
                       "median": statistics.median(latency) if latency else None,
                       "p95": latency[math.ceil(.95 * len(latency)) - 1] if latency else None,
                       "max": max(latency) if latency else None},
    }


def format_report(report):
    def percent(value): return "n/a" if value is None else f"{value:.1%}"
    lines = [f"Scheduled: {report['total_scheduled_evaluations']}; completed: {report['completed_evaluations']}; "
             f"OK: {report['ok_count']}; recovered: {report['recovered_count']}; failed: {report['failed_count']}",
             "Completion rate: " + percent(report["completion_rate"]),
             f"Non-evaluation failures: {report['non_evaluation_failure_events']}; "
             f"duplicates ignored: {report['duplicate_events_ignored']}; ignored lines: {report['unrelated_or_malformed_lines_ignored']}"]
    for route, row in report["routing"]["routes"].items():
        lines.append(f"Route {route}: {row['count']} ({percent(row['rate'])})")
    method = report["methodology"]
    lines.append(f"Hard fail: {method['hard_fail_count']} ({percent(method['hard_fail_rate'])})")
    lines.append("HF frequency: " + ", ".join(f"{key}={count}" for key, count in method["hf_frequency"].items()))
    for key, distribution in method["score_distribution"].items():
        lines.append("Scores " + key + ": " + ", ".join(f"{value}={count}" for value, count in distribution.items()))
    reliability = report["reliability"]
    lines.append("First-pass valid: " + percent(reliability["first_pass_contract_valid_rate"]) +
                 "; final valid: " + percent(reliability["final_contract_valid_rate"]))
    for key in ("retry_attempted", "retry_recovered"):
        lines.append(f"{key}: {reliability[key+'_count']} ({percent(reliability[key+'_rate'])})")
    lines.append("Error kinds: " + (", ".join(f"{key}={count}" for key, count in reliability["evaluator_error_kind_frequencies"].items()) or "none"))
    lines.append("Latency ms: " + ", ".join(f"{key}={value if value is not None else 'n/a'}" for key, value in report["latency_ms"].items()))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", nargs="?", help="DEV log file; omitted or - reads stdin")
    parser.add_argument("--json", action="store_true", help="Aggregate JSON only; never raw events or hashes")
    args = parser.parse_args(argv)
    try:
        if args.log_file in (None, "-"):
            report = summarize(sys.stdin)
        else:
            path = Path(args.log_file)
            # Reads are confined to DEV; symlinks cannot turn the CLI into an external reader.
            root = Path(__file__).resolve().parents[1]
            path = path if path.is_absolute() else root / path
            if ".." in path.parts or not path.resolve().is_relative_to(root):
                raise ValueError("outside DEV")
            with path.open(encoding="utf-8", errors="replace") as log_file:
                report = summarize(log_file)
    except (OSError, ValueError, RuntimeError, UnicodeError):
        print("FAIL: unable to read a log file inside the DEV repository.", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
