"""Offline fake-model qualification and safe transport regressions."""
import copy
import importlib.util
import json
import socket
import sys
from pathlib import Path
from urllib import request, error
import pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.quality_evaluation.contract import DIMENSIONS, FLAG_DIMENSIONS, validate_result
from services.quality_evaluation.prompt import QualityPromptBuilder
from services.quality_evaluation.model_adapter import AdapterError, ModelConfig, ModelReply, OpenAICompatibleAdapter
from services.quality_evaluation.qualification import load_labeled_cases, qualify, select_cases, write_report
from services.quality_evaluation.metrics import calculate_metrics, compare_results, qualification_outcome
from services.quality_evaluation.repair import retry_messages

CASES = load_labeled_cases()
CASE = next(c for c in CASES if c["id"] == "specific_grounded_reflection")
CONFIG = ModelConfig("fake", "https://example.invalid/v1", api_key_env="QUALITY_TEST_KEY")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(request.OpenerDirector, "open", forbidden)
    monkeypatch.setenv("QUALITY_TEST_KEY", "sk-test-quality-secret")


class Fake:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
    def complete(self, messages, *, live=False):
        assert live is True
        self.calls.append(copy.deepcopy(messages))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return ModelReply(reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False), "{}")


def run(replies, cases=None):
    model = Fake(replies)
    report = qualify(cases or [CASE], QualityPromptBuilder(), model, CONFIG, live=True)
    return report, model


def cli():
    spec = importlib.util.spec_from_file_location("quality_cli", ROOT / "tests/run_quality_model_qualification.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_dry_run_no_calls_no_artifacts(monkeypatch):
    module = cli()
    monkeypatch.setattr(module, "OpenAICompatibleAdapter", lambda *a: pytest.fail("adapter instantiated"))
    monkeypatch.setattr(module, "write_report", lambda *a, **k: pytest.fail("artifact write"))
    original_get = module.os.environ.get
    def guarded_get(name, *args):
        if name in ("OPENAI_API_KEY", "QUALITY_TEST_KEY"):
            pytest.fail("credential lookup")
        return original_get(name, *args)
    monkeypatch.setattr(module.os.environ, "get", guarded_get)
    assert module.main([]) == 0
    assert module.main(["--dry-run", "--max-cases", "1"]) == 0
    model = Fake([])
    assert qualify([CASE], QualityPromptBuilder(), model, CONFIG)["network_calls"] == 0
    assert model.calls == []


@pytest.mark.parametrize("args", [["--live"], ["--live", "--model", "fake"], ["--live", "--model", "fake", "--base-url", "https://example.invalid/v1"]])
def test_live_requires_config_and_credentials(args, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli().main(args) == 2


def test_qualify_live_requires_credentials(monkeypatch):
    monkeypatch.delenv("QUALITY_TEST_KEY")
    model = Fake([])
    with pytest.raises(AdapterError, match="missing_api_key"):
        qualify([CASE], QualityPromptBuilder(), model, CONFIG, live=True)
    assert not model.calls


def variant(kind):
    value = copy.deepcopy(CASE["expected"])
    if kind == "detail":
        value["reason"] = "Другая формулировка."
    if kind in ("score", "flag", "both", "overall"):
        value["scores"]["naturalness"] = 1
        value["overall_quality"] = "acceptable"
    if kind in ("flag", "both"):
        value["quality_flags"] = [{"flag_id": "Q06_TEMPLATE_LANGUAGE", "evidence": CASE["input"]["candidate_response"]}]
    if kind == "both":
        value["scores"]["progression"] = 1
    if kind == "overall":
        value["scores"]["naturalness"] = 0
        value["overall_quality"] = "weak"
    return value


@pytest.mark.parametrize("kind,label", [("exact", "EXACT_MATCH"), ("detail", "QUALITY_MATCH_DETAIL_VARIANCE"),
    ("score", "OVERALL_MATCH_SCORE_VARIANCE"), ("flag", "OVERALL_MATCH_FLAG_VARIANCE"),
    ("both", "OVERALL_MATCH_SCORE_AND_FLAG_VARIANCE"), ("overall", "QUALITY_SEMANTIC_MISMATCH")])
def test_classification(kind, label):
    expected = variant("score") if kind in ("score", "flag", "both") else copy.deepcopy(CASE["expected"])
    actual = variant(kind)
    if kind == "score":
        actual["scores"]["progression"] = 1
    validate_result(actual, CASE["input"])
    validate_result(expected, CASE["input"])
    assert qualification_outcome(True, compare_results(actual, expected)) == label


@pytest.mark.parametrize("kind", ["detail", "score", "flag", "both", "overall"])
def test_no_retry_semantic_disagreement(kind):
    report, model = run([variant(kind)])
    assert report["cases"][0]["contract_valid"]
    assert len(model.calls) == 1


def test_malformed_json_repair_and_reliability():
    report, model = run(["{", CASE["expected"]])
    row = report["cases"][0]
    assert row["first_attempt"]["error"]["kind"] == "malformed_json"
    assert row["recovered"] and row["attempt_count"] == 2
    metrics = report["metrics"]
    assert metrics["first_pass_contract_valid_rate"] == 0
    assert metrics["first_pass_infrastructure_failures"] == 1
    assert metrics["final_contract_valid_rate"] == metrics["retry_recovery_rate"] == 1
    assert metrics["retry_attempted_cases"] == metrics["retry_recovered_cases"] == 1
    assert metrics["final_infrastructure_failures"] == 0
    assert model.calls[1][:-1] == model.calls[0]
    repair = model.calls[1][-1]["content"]
    assert CASE["expected"]["reason"] not in repair
    for marker in [*FLAG_DIMENSIONS, *DIMENSIONS, "strong", "acceptable", "weak", "overall_quality"]:
        assert marker not in repair


@pytest.mark.parametrize("mutation", ["missing", "unknown", "shape", "flag_shape", "null", "context"])
def test_repairable_contract_recovery(mutation):
    invalid = copy.deepcopy(CASE["expected"])
    if mutation == "missing":
        del invalid["reason"]
    elif mutation == "unknown":
        invalid["secret_gold_injection"] = "strong Q01_GENERIC_REFLECTION"
    elif mutation == "shape":
        invalid["scores"] = []
    elif mutation == "flag_shape":
        invalid["quality_flags"] = [{}]
    elif mutation == "null":
        invalid["scores"]["progression"] = None
    elif mutation == "context":
        invalid["insufficient_context"]["present"] = True
    report, model = run([invalid, CASE["expected"]])
    assert report["cases"][0]["recovered"]
    assert "secret_gold_injection" not in model.calls[1][-1]["content"]
    assert "strong" not in model.calls[1][-1]["content"]


@pytest.mark.parametrize("mutation", ["score", "flag", "evidence", "overall", "flag_score", "context_dimension"])
def test_unrecoverable_contract_errors(mutation):
    invalid = variant("flag")
    if mutation == "score":
        invalid["scores"]["progression"] = 9
    elif mutation == "flag":
        invalid["quality_flags"][0]["flag_id"] = "Q99_UNKNOWN"
    elif mutation == "evidence":
        invalid["quality_flags"][0]["evidence"] = "absent synthetic evidence"
    elif mutation == "overall":
        invalid["overall_quality"] = "strong"
    elif mutation == "flag_score":
        invalid["scores"]["naturalness"] = 2
    else:
        invalid["insufficient_context"] = {"present": True, "items": [{"dimensions": ["unknown"], "missing": "x", "reason": "x"}]}
    report, model = run([invalid])
    assert report["cases"][0]["outcome"] == "INFRA_FAIL"
    assert len(model.calls) == 1


@pytest.mark.parametrize("kind", ["timeout", "transport_error", "http_error", "provider_error", "response_format_error", "empty_response", "truncated_response"])
def test_infrastructure_subtypes_and_bounded_retry(kind):
    report, model = run([AdapterError(kind), AdapterError(kind)])
    row = report["cases"][0]
    assert row["outcome"] == "INFRA_FAIL"
    assert row["error"]["kind"] == kind
    assert len(model.calls) == (2 if kind in ("empty_response", "truncated_response") else 1)


def test_malformed_bounded_two_attempts():
    report, model = run(["{", "{", CASE["expected"]])
    assert len(model.calls) == 2
    assert report["cases"][0]["outcome"] == "INFRA_FAIL"


class Response:
    status = 200
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return self.raw[:size]


@pytest.mark.parametrize("payload,kind", [
    ({"error": {"message": "failure"}}, "provider_error"),
    ({"choices": [{"message": {"content": "", "reasoning": "{valid: true}"}}]}, "empty_response"),
    ({"choices": [{"message": {"content": json.dumps(CASE["expected"])}, "finish_reason": "length"}]}, "truncated_response"),
])
def test_safe_adapter_envelopes(payload, kind):
    adapter = OpenAICompatibleAdapter(CONFIG, transport=lambda *a, **k: Response(payload))
    with pytest.raises(AdapterError) as exc:
        adapter.complete([], live=True)
    assert exc.value.kind == kind


def test_reasoning_never_result():
    payload = {"choices": [{"message": {"content": "{", "reasoning": json.dumps(CASE["expected"])}}]}
    adapter = OpenAICompatibleAdapter(CONFIG, transport=lambda *a, **k: Response(payload))
    report = qualify([CASE], QualityPromptBuilder(), adapter, CONFIG, live=True)
    assert report["cases"][0]["outcome"] == "INFRA_FAIL"
    assert "reasoning" not in json.loads(report["cases"][0]["raw_response"])["choices"][0]["message"]


def test_metrics_all_corpus_exact():
    report, _ = run([c["expected"] for c in CASES], CASES)
    m = report["metrics"]
    assert m["exact_full_result_match_count"] == m["overall_quality_agreement_count"] == 22
    assert m["overall_quality_agreement_rate"] == 1
    assert sum(sum(row.values()) for row in m["overall_quality_confusion_matrix"].values()) == 22
    for dimension in DIMENSIONS:
        row = m["dimensions"][dimension]
        assert row["agreement_count"] == 22 and row["agreement_rate"] == 1
        assert sum(sum(r.values()) for r in row["confusion_matrix"].values()) == 22
    for flag in FLAG_DIMENSIONS:
        row = m["quality_flags"][flag]
        assert row["tp"] == sum(any(f["flag_id"] == flag for f in c["expected"]["quality_flags"]) for c in CASES)
        assert row["fp"] == row["fn"] == 0
        assert row["precision"] == row["recall"] == 1


def test_metrics_variance_and_null():
    case = copy.deepcopy(CASE)
    case["expected"] = variant("flag")
    actual = variant("score")
    actual["scores"]["progression"] = 1
    report, _ = run([actual], [case])
    m = report["metrics"]
    assert m["dimensions"]["progression"]["confusion_matrix"]["2"]["1"] == 1
    assert m["quality_flags"]["Q06_TEMPLATE_LANGUAGE"]["fn"] == 1
    assert m["quality_flags"]["Q06_TEMPLATE_LANGUAGE"]["recall"] == 0
    report, _ = run([variant("flag")])
    assert report["metrics"]["quality_flags"]["Q06_TEMPLATE_LANGUAGE"]["fp"] == 1
    assert report["metrics"]["overall_quality_confusion_matrix"]["strong"]["acceptable"] == 1


def test_zero_denominators():
    m = calculate_metrics([], 0)
    assert m["overall_quality_agreement_rate"] is None
    assert m["retry_recovery_rate"] is None
    assert m["final_contract_valid_rate"] is None
    for row in m["dimensions"].values():
        assert row["agreement_rate"] is None
    for row in m["quality_flags"].values():
        assert row["precision"] is row["recall"] is None


def test_artifacts_sanitized(tmp_path):
    testdir = tmp_path / "tests"
    testdir.mkdir()
    (testdir / "response_quality_evaluator_cases.json").write_bytes((ROOT / "tests/response_quality_evaluator_cases.json").read_bytes())
    report, _ = run([CASE["expected"]])
    report["cases"][0]["raw_response"] = json.dumps({"headers": {"Authorization": "Bearer sk-test-quality-secret"},
        "env": {"ANY_ENV": "private"}, "reasoning": "hidden", "message": "sk-test-quality-secret"})
    path = write_report(report, project_root=tmp_path, secret="sk-test-quality-secret")
    text = path.read_text()
    assert "sk-test-quality-secret" not in text and "Authorization" not in text and "ANY_ENV" not in text
    assert "hidden" not in text
    assert path.parent == tmp_path / "artifacts/evaluation/quality"
    data = json.loads(text)
    assert data["cases"][0]["final_selected_result"] == CASE["expected"]
    assert data["cases"][0]["first_attempt"]["validated_result"] == CASE["expected"]
    assert "metrics" in data and data["metadata"]["model"] == "fake"


def test_dry_run_write_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_report({"dry_run": True}, project_root=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("ids,maximum", [(["unknown"], None), ([CASE["id"], CASE["id"]], None), (None, 0)])
def test_selection_rejected(ids, maximum):
    with pytest.raises(ValueError):
        select_cases(CASES, ids, maximum)


def test_cli_alias_and_selection():
    assert cli().main(["--max-output-tokens", "123", "--reasoning-effort", "low", "--case-id", CASE["id"], "--max-cases", "1"]) == 0
