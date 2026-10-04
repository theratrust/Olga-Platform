"""Contract and CLI regression tests using the unchanged synthetic corpus."""

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.evaluation import ContractError, load_corpus, validate_case, validate_result

CORPUS_PATH = PROJECT_ROOT / "tests/coaching_evaluator_cases.json"
CORPUS = load_corpus(CORPUS_PATH)
CASES = {case["id"]: case for case in CORPUS["cases"]}


def validate(case):
    return validate_result(case["expected"], case["input"]["candidate_response"], PROJECT_ROOT)


@pytest.mark.parametrize("case_id", list(CASES))
def test_existing_corpus(case_id):
    validate_case(copy.deepcopy(CASES[case_id]), PROJECT_ROOT)


@pytest.mark.parametrize("case_id,overall,decision", [
    ("advice_pass", "pass", "accept"),
    ("advice_fail", "fail", "retry"),
    ("diagnosis_tentative", "fail", "escalate"),
    ("impersonation_fail", "fail", "escalate"),
    ("review_repetitive_reflection", "review", "escalate"),
    ("missing_prior_hypothesis", "insufficient_context", "insufficient_context"),
    ("mixed_advice_missing_fear_context", "fail", "retry"),
])
def test_valid_priority_outcomes(case_id, overall, decision):
    result = validate(CASES[case_id])
    assert (result["overall"], result["decision"]) == (overall, decision)


@pytest.mark.parametrize("field,value,error", [
    ("excerpt", "not in response", "exact substring"),
    ("rule_id", "HF09", "rule_id"),
])
def test_invalid_violation(field, value, error):
    case = copy.deepcopy(CASES["advice_fail"])
    case["expected"]["violations"][0][field] = value
    with pytest.raises(ContractError, match=error):
        validate(case)


@pytest.mark.parametrize("score", [-1, 3, 1.0, True, False, "2", [], {}])
def test_invalid_score(score):
    case = copy.deepcopy(CASES["advice_pass"])
    case["expected"]["scores"]["grounding"] = score
    with pytest.raises(ContractError, match="scores"):
        validate(case)


def test_missing_top_level_reference():
    case = copy.deepcopy(CASES["archetype_fail"])
    case["expected"]["source_refs"] = [case["expected"]["source_refs"][0]]
    with pytest.raises(ContractError, match="missing from top-level"):
        validate(case)


@pytest.mark.parametrize("case_id", ["advice_pass", "advice_fail"])
def test_inconsistent_hard_fail(case_id):
    case = copy.deepcopy(CASES[case_id])
    case["expected"]["hard_fail"] = not case["expected"]["hard_fail"]
    with pytest.raises(ContractError, match="hard_fail"):
        validate(case)


def test_invalid_pass_with_null_score():
    case = copy.deepcopy(CASES["advice_pass"])
    case["expected"]["scores"]["grounding"] = None
    with pytest.raises(ContractError, match="null scores"):
        validate(case)


@pytest.mark.parametrize("case_id,decision", [
    ("diagnosis_tentative", "retry"),
    ("impersonation_fail", "retry"),
    ("advice_fail", "escalate"),
    ("mixed_advice_missing_fear_context", "insufficient_context"),
    ("advice_pass", "insufficient_context"),
    ("review_repetitive_reflection", "accept"),
])
def test_invalid_decision_priority(case_id, decision):
    case = copy.deepcopy(CASES[case_id])
    case["expected"]["decision"] = decision
    with pytest.raises(ContractError, match="decision"):
        validate(case)


@pytest.mark.parametrize("path", [
    "/etc/passwd", "knowledge/method/../../requirements.txt",
    "knowledge/methodology/file.md", "knowledge/method/../method/границы.md",
    "knowledge//method/границы.md", "knowledge/method/./границы.md",
    "knowledge\\method\\границы.md",
])
def test_malformed_source_path(path):
    case = copy.deepcopy(CASES["advice_pass"])
    case["expected"]["source_refs"][0]["path"] = path
    with pytest.raises(ContractError, match="path"):
        validate(case)


def test_duplicate_references_normalized_without_mutation():
    case = copy.deepcopy(CASES["advice_fail"])
    result = case["expected"]
    for refs in [result["source_refs"], result["violations"][0]["source_refs"]]:
        refs.append(copy.deepcopy(refs[0]))
    original = copy.deepcopy(case)
    normalized = validate(case)
    assert len(normalized["source_refs"]) == 1
    assert len(normalized["violations"][0]["source_refs"]) == 1
    assert case == original


@pytest.mark.parametrize("mutation,error", [
    (lambda r: r["scores"].pop("grounding"), "scores"),
    (lambda r: r["scores"].update(extra=2), "scores"),
    (lambda r: r.update(extra=True), "result"),
    (lambda r: r.update(hard_fail=1), "boolean"),
    (lambda r: r.update(overall="unknown"), "overall"),
    (lambda r: r.update(decision="unknown"), "decision"),
    (lambda r: r.update(overall="review"), "overall"),
    (lambda r: r["scores"].update(grounding=0), "critical violation"),
    (lambda r: r["source_refs"][0].update(section="invented heading"), "heading"),
    (lambda r: r["source_refs"][0].update(provenance="derived_evaluation_rule"), "provenance"),
    (lambda r: r["insufficient_context"].update(present=True), "flag"),
])
def test_additional_strict_invariants(mutation, error):
    case = copy.deepcopy(CASES["advice_pass"])
    mutation(case["expected"])
    with pytest.raises(ContractError, match=error):
        validate(case)


def test_hard_fail_not_hidden_by_perfect_scores():
    case = copy.deepcopy(CASES["advice_fail"])
    case["expected"]["scores"] = dict.fromkeys(case["expected"]["scores"], 2)
    assert validate(case)["decision"] == "retry"
    case["expected"].update(overall="pass", decision="accept")
    with pytest.raises(ContractError, match="overall"):
        validate(case)


def test_escalation_takes_priority_over_other_violation_and_context():
    case = copy.deepcopy(CASES["mixed_advice_missing_fear_context"])
    diagnosis = CASES["diagnosis_tentative"]
    case["input"]["candidate_response"] += " " + diagnosis["input"]["candidate_response"]
    case["expected"]["violations"].extend(copy.deepcopy(diagnosis["expected"]["violations"]))
    case["expected"]["source_refs"].extend(copy.deepcopy(diagnosis["expected"]["source_refs"]))
    case["expected"]["decision"] = "escalate"
    assert validate(case)["insufficient_context"]["present"] is True


def runner_module():
    spec = importlib.util.spec_from_file_location(
        "offline_corpus_runner", PROJECT_ROOT / "tests/run_coaching_evaluator_cases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_success(capsys):
    assert runner_module().main([str(CORPUS_PATH)]) == 0
    output = capsys.readouterr().out
    assert output.count("PASS ") == 22
    assert "22/22 passed; 0 failed" in output


@pytest.mark.parametrize("kind", ["invalid_case", "duplicate_id", "malformed_json",
                                 "duplicate_key", "nonstandard_constant"])
def test_runner_failure(kind, capsys):
    data = copy.deepcopy(CORPUS)
    if kind == "invalid_case":
        data["cases"][0]["expected"]["decision"] = "accept"
    if kind == "duplicate_id":
        data["cases"][1]["id"] = data["cases"][0]["id"]
    content = json.dumps(data, ensure_ascii=False)
    if kind == "malformed_json":
        content = "{"
    if kind == "duplicate_key":
        content = '{"cases": [], "cases": []}'
    if kind == "nonstandard_constant":
        content = '{"cases": NaN}'
    # Temporary fixtures stay inside the authorized DEV repository.
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "tests") as directory:
        path = Path(directory) / "corpus.json"
        path.write_text(content, encoding="utf-8")
        assert runner_module().main([str(path)]) == 1
    output = capsys.readouterr().out
    assert "FAIL " in output
    if kind == "invalid_case":
        assert "21/22 passed; 1 failed" in output


def test_source_symlink_escape():
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "tests") as directory:
        root = Path(directory)
        method = root / "knowledge/method"
        method.mkdir(parents=True)
        outside = root / "outside.md"
        outside.write_text("# Topic\n", encoding="utf-8")
        (method / "linked.md").symlink_to(outside)
        case = copy.deepcopy(CASES["advice_pass"])
        case["expected"]["source_refs"] = [{
            "path": "knowledge/method/linked.md", "section": "Topic",
            "provenance": "validated_method_rule",
        }]
        with pytest.raises(ContractError, match="escapes method directory"):
            validate_result(case["expected"], case["input"]["candidate_response"], root)


@pytest.mark.parametrize("field", ["hard_fail", "violations", "scores", "overall",
                                  "decision", "reason", "source_refs", "insufficient_context"])
def test_missing_top_level_result_field(field):
    case = copy.deepcopy(CASES["advice_fail"])
    del case["expected"][field]
    with pytest.raises(ContractError, match="result: invalid fields"):
        validate(case)


@pytest.mark.parametrize("field", ["rule_id", "excerpt", "reason", "source_refs"])
def test_missing_nested_violation_field(field):
    case = copy.deepcopy(CASES["advice_fail"])
    del case["expected"]["violations"][0][field]
    with pytest.raises(ContractError, match="invalid fields"):
        validate(case)


@pytest.mark.parametrize("mutation,error", [
    (lambda r: r["insufficient_context"]["items"].__setitem__(0, "invalid"), "expected object"),
    (lambda r: r["insufficient_context"]["items"][0].pop("missing"), "invalid fields"),
    (lambda r: r["insufficient_context"]["items"][0].update(rule_ids=["HF99"]), "rule_ids"),
    (lambda r: r["insufficient_context"]["items"][0].update(rule_ids=[]), "must not be empty"),
    (lambda r: r["insufficient_context"]["items"][0].update(rule_ids="HF03"), "expected array"),
    (lambda r: r["insufficient_context"].update(present=1), "expected boolean"),
    (lambda r: r["insufficient_context"].update(present=False), "flag"),
])
def test_malformed_insufficient_context(mutation, error):
    case = copy.deepcopy(CASES["missing_prior_hypothesis"])
    mutation(case["expected"])
    with pytest.raises(ContractError, match=error):
        validate(case)


@pytest.mark.parametrize("field", ["reason", "excerpt"])
@pytest.mark.parametrize("value", ["", " \t\n"])
def test_empty_violation_text(field, value):
    case = copy.deepcopy(CASES["advice_fail"])
    case["expected"]["violations"][0][field] = value
    with pytest.raises(ContractError, match=field):
        validate(case)


@pytest.mark.parametrize("value", ["", " \t\n"])
def test_empty_top_level_reason(value):
    case = copy.deepcopy(CASES["advice_pass"])
    case["expected"]["reason"] = value
    with pytest.raises(ContractError, match="reason"):
        validate(case)


@pytest.mark.parametrize("nested", [False, True])
def test_empty_required_source_refs(nested):
    case = copy.deepcopy(CASES["advice_fail"])
    obj = case["expected"]["violations"][0] if nested else case["expected"]
    obj["source_refs"] = []
    with pytest.raises(ContractError, match="source_refs: must not be empty"):
        validate(case)


@pytest.mark.parametrize("path,error", [
    ("knowledge/method/absent_source_for_contract_test.md", "does not exist"),
    ("knowledge/method/bad\x00.md", "embedded NUL"),
])
def test_source_path_failure_is_contract_error(path, error):
    case = copy.deepcopy(CASES["advice_pass"])
    case["expected"]["source_refs"][0]["path"] = path
    with pytest.raises(ContractError, match=error):
        validate(case)


@pytest.mark.parametrize("operation", ["resolve", "is_file", "read_text"])
@pytest.mark.parametrize("error", [OSError("filesystem failure"), ValueError("invalid path"),
                                  RuntimeError("symlink loop"), PermissionError("access denied")])
def test_source_filesystem_errors_translated(monkeypatch, operation, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(Path, operation, fail)
    with pytest.raises(ContractError, match="source path validation failed|cannot read source"):
        validate(CASES["advice_pass"])


@pytest.mark.parametrize("path", [
    str(PROJECT_ROOT / "requirements.txt"),
    "tests/../tests/coaching_evaluator_cases.json",
    "../tests/coaching_evaluator_cases.json",
])
def test_cli_corpus_path_rejected(path, capsys):
    assert runner_module().main([path]) == 1
    output = capsys.readouterr().out
    assert "FAIL corpus: corpus path:" in output
    assert "Summary:" in output


def test_cli_corpus_symlink_escape(capsys):
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "tests") as directory:
        link = Path(directory) / "corpus.json"
        link.symlink_to(PROJECT_ROOT / "requirements.txt")
        assert runner_module().main([str(link)]) == 1
    assert "symlink escapes repository tests/" in capsys.readouterr().out


def test_method_directory_symlink_escape():
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "tests") as directory:
        root = Path(directory)
        project = root / "project"
        (project / "knowledge").mkdir(parents=True)
        (project / "knowledge/method").symlink_to(PROJECT_ROOT / "knowledge/method", target_is_directory=True)
        with pytest.raises(ContractError, match="method directory escapes project root"):
            validate_result(CASES["advice_pass"]["expected"],
                            CASES["advice_pass"]["input"]["candidate_response"], project)


def test_input_unchanged_on_failure_after_normalization():
    case = copy.deepcopy(CASES["advice_fail"])
    case["expected"]["source_refs"].append(copy.deepcopy(case["expected"]["source_refs"][0]))
    case["expected"]["decision"] = "accept"
    original = copy.deepcopy(case)
    with pytest.raises(ContractError, match="decision"):
        validate(case)
    assert case == original


def test_returned_nested_structures_independent():
    case = copy.deepcopy(CASES["mixed_advice_missing_fear_context"])
    original = copy.deepcopy(case)
    result = validate(case)
    result["scores"]["client_authorship"] = 2
    result["source_refs"][0]["section"] = "changed"
    result["violations"][0]["source_refs"][0]["section"] = "changed"
    result["insufficient_context"]["items"][0]["rule_ids"].append("HF08")
    assert case == original


def test_pass_rejected_with_context_flag_and_perfect_scores():
    case = copy.deepcopy(CASES["missing_prior_hypothesis"])
    case["expected"]["scores"] = dict.fromkeys(case["expected"]["scores"], 2)
    case["expected"].update(overall="pass", decision="accept")
    with pytest.raises(ContractError, match="overall: expected insufficient_context"):
        validate(case)


@pytest.mark.parametrize("content", ["", " ", "Сообщение"])
def test_context_content_accepts_empty_string(content):
    case = copy.deepcopy(CASES["advice_pass"])
    case["input"]["conversation_context"] = [{"role": "user", "content": content}]
    validate_case(case, PROJECT_ROOT)


def test_context_content_rejects_nonstring():
    case = copy.deepcopy(CASES["advice_pass"])
    case["input"]["conversation_context"] = [{"role": "user", "content": None}]
    with pytest.raises(ContractError, match="expected string"):
        validate_case(case, PROJECT_ROOT)


def test_runner_continues_after_embedded_nul_source_path(capsys):
    data = copy.deepcopy(CORPUS)
    data["cases"][0]["expected"]["source_refs"][0]["path"] = "knowledge/method/bad\x00.md"
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "tests") as directory:
        path = Path(directory) / "corpus.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert runner_module().main([str(path)]) == 1
    output = capsys.readouterr().out
    assert "FAIL advice_fail:" in output
    assert "PASS mixed_advice_missing_fear_context" in output
    assert "21/22 passed; 1 failed" in output


def test_relative_corpus_path_uses_project_root(monkeypatch):
    monkeypatch.chdir(PROJECT_ROOT / "tests")
    assert len(load_corpus("tests/coaching_evaluator_cases.json")["cases"]) == 22
