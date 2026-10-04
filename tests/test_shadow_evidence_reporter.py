"""Synthetic shadow-log aggregation only; no runtime imports or live providers."""

import copy
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shadow_evidence_reporter", ROOT / "scripts/report_shadow_evaluations.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def event(kind="OK", index=1, **changes):
    row = {"timestamp": f"2026-10-04T14:00:{index:02d}+00:00", "mode": "shadow",
           "event": "SHADOW_EVAL_" + kind, "candidate_hash": "a" * 64, "session_hash": "b" * 64}
    if kind != "SCHEDULED":
        row.update(hard_fail=False, violations=[], scores={key: 2 for key in reporter.SCORES},
                   shadow_route="accept", first_pass_contract_valid=kind == "OK", retry_attempted=kind == "RECOVERED",
                   retry_recovered=kind == "RECOVERED", final_contract_valid=kind != "FAIL", latency_ms=100,
                   evaluator_error_kind="timeout" if kind == "FAIL" else None)
    row.update(changes)
    return row


def line(row):
    return "olga_bot_container_dev | INFO:services.evaluation.runtime:" + row["event"] + " " + json.dumps(row, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("kind,key", [("OK", "ok_count"), ("RECOVERED", "recovered_count"), ("FAIL", "failed_count")])
def test_terminal_event_parsing(kind, key):
    result = reporter.summarize([line(event(kind))])
    assert result["completed_evaluations"] == result[key] == 1
    assert result["total_scheduled_evaluations"] == 0
    assert result["completion_rate"] is None


def test_scheduled_only_is_not_a_completion():
    result = reporter.summarize([line(event("SCHEDULED"))])
    assert result["total_scheduled_evaluations"] == 1
    assert result["completed_evaluations"] == 0 and result["completion_rate"] == 0
    assert result["reliability"]["final_contract_valid_rate"] is None


def test_route_aggregation_and_completion_rate():
    rows = [line(event("SCHEDULED", 0))]
    for index, route in enumerate(reporter.ROUTES, 1):
        rows.append(line(event(index=index, shadow_route=route)))
    rows.append(line(event("FAIL", 5, shadow_route="retry")))
    result = reporter.summarize(rows)
    assert result["completed_evaluations"] == 5
    # A partial log window can contain more terminal than scheduled events; do not clamp.
    assert result["completion_rate"] == 5
    for route in reporter.ROUTES:
        assert result["routing"]["routes"][route] == {"count": 1, "rate": .25}
    assert result["routing"]["denominator_final_valid"] == 4


def test_hf_frequency_and_hard_fail_rate():
    rows = [line(event(index=1, hard_fail=True, violations=["HF01", "HF04", "HF04"])),
            line(event(index=2, hard_fail=True, violations=["HF04", "HF08"])),
            line(event(index=3)), line(event("FAIL", 4, hard_fail=True, violations=["HF05"]))]
    result = reporter.summarize(rows)["methodology"]
    assert result["hard_fail_count"] == 2 and result["hard_fail_rate"] == 2 / 3
    assert result["hf_frequency"] == {"HF01": 1, "HF02": 0, "HF03": 0, "HF04": 2, "HF05": 0, "HF06": 0, "HF07": 0, "HF08": 1}


def test_score_distribution_including_null_and_missing():
    rows = [line(event(index=i+1, scores={key: value for key in reporter.SCORES}))
            for i, value in enumerate((0, 1, 2, None))]
    rows.append(line(event(index=5, scores={"grounding": True})))
    result = reporter.summarize(rows)["methodology"]["score_distribution"]
    for key in reporter.SCORES:
        assert result[key] == {"0": 1, "1": 1, "2": 1, "null": 1}


def test_latency_mean_median_nearest_rank_p95_and_max():
    rows = [line(event(index=i+1, latency_ms=(i+1)*10)) for i in range(20)]
    result = reporter.summarize(rows)["latency_ms"]
    assert result == {"count": 20, "mean": 105, "median": 105, "p95": 190, "max": 200}


def test_retry_reliability_and_error_frequencies():
    rows = [line(event(index=1)), line(event("RECOVERED", 2)),
            line(event("FAIL", 3, retry_attempted=True, retry_recovered=False, evaluator_error_kind="malformed_model_json"))]
    result = reporter.summarize(rows)["reliability"]
    assert result["first_pass_contract_valid_rate"] == 1 / 3
    assert result["retry_attempted_count"] == 2 and result["retry_attempted_rate"] == 2 / 3
    assert result["retry_recovered_count"] == 1 and result["retry_recovered_rate"] == .5
    assert result["final_contract_valid_rate"] == 2 / 3
    assert result["evaluator_error_kind_frequencies"] == {"malformed_model_json": 1}


def test_repeated_ingestion_deduplicates_schedule_and_terminal_separately():
    scheduled = event("SCHEDULED", 1)
    completed = event(index=2)
    rows = [line(scheduled), line(completed)] * 3
    rows.append(line(event(index=3)))  # Identical hashes but different time: legitimate new evaluation.
    result = reporter.summarize(rows)
    assert result["total_scheduled_evaluations"] == 1 and result["completed_evaluations"] == 2
    assert result["duplicate_events_ignored"] == 4


def test_duplicate_without_hashes_and_with_equivalent_timezone_is_stable():
    row = event("FAIL", 1, candidate_hash=None, session_hash=None)
    duplicate = copy.deepcopy(row)
    duplicate["timestamp"] = "2026-10-04T16:00:01+02:00"
    result = reporter.summarize([line(row), line(duplicate)])
    assert result["completed_evaluations"] == 1 and result["duplicate_events_ignored"] == 1


@pytest.mark.parametrize("bad", ["unrelated Docker startup", "SHADOW_EVAL_OK {broken}", "[]", "null",
                                 '{"event":"SHADOW_EVAL_OK","mode":"shadow"}',
                                 '{"event":"SHADOW_EVAL_OK","mode":"shadow","timestamp":"invalid"}',
                                 'SHADOW_EVAL_FAIL ' + json.dumps(event()),
                                 json.dumps(event(timestamp="2026-10-04T14:00:01")),
                                 '{"event":"SHADOW_EVAL_OK","event":"SHADOW_EVAL_FAIL"}'])
def test_malformed_and_unrelated_lines_ignored_safely(bad):
    assert reporter.parse_event(bad) is None
    assert reporter.summarize([bad])["completed_evaluations"] == 0


def test_mixed_unrelated_docker_logs():
    rows = ["database startup\n", line(event("SCHEDULED", 0)), "network retry by unrelated subsystem\n",
            line(event()), "bot sent a response\n"]
    result = reporter.summarize(rows)
    assert result["total_scheduled_evaluations"] == result["completed_evaluations"] == 1
    assert result["unrelated_or_malformed_lines_ignored"] == 3


def test_non_evaluation_failures_not_counted_as_completed():
    row = {"timestamp": "2026-10-04T14:00:00+00:00", "mode": "shadow", "event": "SHADOW_EVAL_FAIL",
           "evaluator_error_kind": "capacity_exceeded"}
    result = reporter.summarize([line(row)])
    assert result["completed_evaluations"] == result["failed_count"] == 0
    assert result["non_evaluation_failure_events"] == 1
    assert result["reliability"]["evaluator_error_kind_frequencies"] == {"capacity_exceeded": 1}


def test_unknown_fields_and_secret_values_never_appear_in_output(monkeypatch, capsys):
    secret = "PRIVATE_API_KEY_DO_NOT_PRINT"
    row = event(evaluator_error_kind=secret, user_message=secret, candidate_response=secret,
                reason=secret, rationale=secret, excerpts=[secret], headers={"Authorization": "Bearer " + secret},
                environment={"API_KEY": secret}, raw_response=secret,
                evaluator_model=secret, scores={"grounding": secret, secret: 1}, violations=[secret, "HF01"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(line(row)))
    assert reporter.main(["--json"]) == 0
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert "Authorization" not in output.out and "a" * 64 not in output.out and "b" * 64 not in output.out
    result = json.loads(output.out)
    assert result["reliability"]["evaluator_error_kind_frequencies"] == {"other_error": 1}
    assert secret not in reporter.format_report(result)


def test_empty_input_has_zero_counts_and_unknown_rates(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert reporter.main([]) == 0
    assert "Scheduled: 0; completed: 0" in capsys.readouterr().out
    result = reporter.summarize([])
    assert result["completion_rate"] is None and result["latency_ms"]["mean"] is None
    assert result["reliability"]["retry_recovered_rate"] is None


def test_supplied_dev_log_file(monkeypatch, capsys):
    with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
        path = Path(directory) / "synthetic.log"
        path.write_text(line(event()))
        assert reporter.main([str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok_count"] == 1


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.log", "SECRET_PATH_NOT_FOR_OUTPUT.log"])
def test_invalid_log_file_errors_do_not_echo_path(capsys, path):
    assert reporter.main([path]) == 2
    output = capsys.readouterr()
    assert path not in output.out + output.err


def test_missing_reliability_fields_remain_unknown():
    row = {"timestamp": "2026-10-04T14:00:00+00:00", "mode": "shadow", "event": "SHADOW_EVAL_FAIL",
           "evaluator_error_kind": "background_exception"}
    result = reporter.summarize([line(row)])
    assert result["failed_count"] == 1
    assert result["reliability"]["first_pass_contract_valid_rate"] is None
    assert result["reliability"]["final_contract_valid_rate"] is None
    assert result["latency_ms"]["count"] == 0


@pytest.mark.parametrize("latency", [-1, True, "SECRET_LATENCY", None])
def test_invalid_latency_is_excluded(latency):
    assert reporter.summarize([line(event(latency_ms=latency))])["latency_ms"]["count"] == 0


def test_log_file_symlink_cannot_escape_dev_repository(capsys):
    with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
        path = Path(directory) / "synthetic.log"
        path.symlink_to("/etc/passwd")
        assert reporter.main([str(path)]) == 2
    assert "passwd" not in capsys.readouterr().err
