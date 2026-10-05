"""Offline derived-quality contract and prompt regressions, without model outputs."""

import ast
import copy
import importlib.util
import json
import socket
import sys
import tempfile
from pathlib import Path
from urllib import request

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.quality_evaluation.contract import (
    DIMENSIONS, FLAG_DIMENSIONS, QualityContractError, load_corpus, validate_case, validate_input, validate_result,
)
from services.quality_evaluation.prompt import QualityPromptBuilder

CORPUS = load_corpus()
CASES = {case["id"]: case for case in CORPUS["cases"]}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Quality foundation must be offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(request.OpenerDirector, "open", forbidden)


def base():
    case = CASES["specific_grounded_reflection"]
    return copy.deepcopy(case["expected"]), copy.deepcopy(case["input"])


@pytest.mark.parametrize("case_id", list(CASES))
def test_all_synthetic_gold_results_validate(case_id):
    case = CASES[case_id]
    assert validate_case(case) == case["expected"]


def test_corpus_covers_dimensions_flags_outcomes_and_conversation_patterns():
    assert len(CORPUS["cases"]) == 22
    assert len(CASES) == 22
    assert {flag["flag_id"] for case in CASES.values() for flag in case["expected"]["quality_flags"]} == set(FLAG_DIMENSIONS)
    assert {case["expected"]["overall_quality"] for case in CASES.values()} == {"strong", "acceptable", "weak", "insufficient_context"}
    assert any("recent_assistant_response_patterns" in case["input"] for case in CASES.values())


@pytest.mark.parametrize("key", ["scores", "quality_flags", "overall_quality", "reason", "insufficient_context"])
def test_missing_result_field_rejected(key):
    result, inp = base()
    del result[key]
    with pytest.raises(QualityContractError): validate_result(result, inp)


@pytest.mark.parametrize("location", ["result", "scores", "gap", "gap_item", "flag", "input", "message"])
def test_unknown_fields_rejected(location):
    case = CASES["weak_with_context_gap"]
    result = copy.deepcopy(case["expected"])
    inp = copy.deepcopy(case["input"])
    targets = {"result": result, "scores": result["scores"], "gap": result["insufficient_context"],
               "gap_item": result["insufficient_context"]["items"][0], "flag": result["quality_flags"][0],
               "input": inp}
    if location == "message":
        inp["conversation_context"] = [{"role": "user", "content": "Текст", "extra": 1}]
    else:
        targets[location]["extra"] = 1
    with pytest.raises(QualityContractError): validate_result(result, inp)


@pytest.mark.parametrize("score", [True, False, -1, 3, "2", 2.0, [], {}])
def test_invalid_scores_rejected(score):
    result, inp = base()
    result["scores"]["progression"] = score
    with pytest.raises(QualityContractError): validate_result(result, inp)


@pytest.mark.parametrize("flag_id", ["HF01", "HF02", "HF03", "HF04", "HF05", "HF06", "HF07", "HF08", "Q99_UNKNOWN", None])
def test_hf_and_unknown_quality_flags_rejected(flag_id):
    result, inp = base()
    result["scores"]["progression"] = 0
    result["overall_quality"] = "weak"
    result["quality_flags"] = [{"flag_id": flag_id, "evidence": inp["candidate_response"]}]
    with pytest.raises(QualityContractError): validate_result(result, inp)


@pytest.mark.parametrize("evidence", ["", "   ", "Не существующая цитата", None])
def test_flag_evidence_must_be_nonempty_exact_anchor(evidence):
    result, inp = base()
    result["scores"]["progression"] = 0
    result["overall_quality"] = "weak"
    result["quality_flags"] = [{"flag_id": "Q04_LOW_PROGRESSION", "evidence": evidence}]
    with pytest.raises(QualityContractError): validate_result(result, inp)


def test_pattern_hint_is_not_quote_evidence():
    result, inp = base()
    inp["recent_assistant_response_patterns"] = ["Обобщённый паттерн без исходной цитаты"]
    result["scores"]["non_repetition"] = 0
    result["overall_quality"] = "weak"
    result["quality_flags"] = [{"flag_id": "Q03_REPETITIVE_STRUCTURE", "evidence": inp["recent_assistant_response_patterns"][0]}]
    with pytest.raises(QualityContractError, match="exact substring"): validate_result(result, inp)


def test_flag_cannot_claim_weakness_on_score_two_and_cannot_repeat():
    result, inp = base()
    flag = {"flag_id": "Q04_LOW_PROGRESSION", "evidence": inp["candidate_response"]}
    result["quality_flags"] = [flag]
    with pytest.raises(QualityContractError, match="concrete weakness"): validate_result(result, inp)
    result["scores"]["progression"] = 0
    result["overall_quality"] = "weak"
    result["quality_flags"] = [flag, flag]
    with pytest.raises(QualityContractError, match="duplicate quality flag"): validate_result(result, inp)


def test_no_question_can_be_strong_and_score_one_does_not_force_flag():
    assert validate_case(CASES["no_question_useful"])["overall_quality"] == "strong"
    result = validate_case(CASES["mild_extra_paraphrase"])
    assert result["overall_quality"] == "acceptable" and result["quality_flags"] == []


@pytest.mark.parametrize("score,overall", [(2, "acceptable"), (1, "strong"), (0, "acceptable"), (0, "insufficient_context")])
def test_overall_consistency(score, overall):
    result, inp = base()
    result["scores"]["progression"] = score
    result["overall_quality"] = overall
    with pytest.raises(QualityContractError, match="overall_quality"): validate_result(result, inp)


def test_null_without_missing_context_rejected():
    result, inp = base()
    result["scores"]["non_repetition"] = None
    result["overall_quality"] = "insufficient_context"
    with pytest.raises(QualityContractError, match="null scores"): validate_result(result, inp)


@pytest.mark.parametrize("mutation", ["false_flag", "empty_items", "wrong_dimension", "no_null", "unknown_dimension", "duplicate_dimension", "missing_reason"])
def test_missing_context_consistency(mutation):
    case = CASES["missing_repetition_history"]
    result, inp = copy.deepcopy(case["expected"]), case["input"]
    gap = result["insufficient_context"]
    if mutation == "false_flag": gap["present"] = False
    elif mutation == "empty_items": gap["items"] = []
    elif mutation == "wrong_dimension": gap["items"][0]["dimensions"] = ["progression"]
    elif mutation == "no_null": result["scores"]["non_repetition"] = 2
    elif mutation == "unknown_dimension": gap["items"][0]["dimensions"] = ["grounding"]
    elif mutation == "duplicate_dimension": gap["items"][0]["dimensions"] *= 2
    elif mutation == "missing_reason": del gap["items"][0]["reason"]
    with pytest.raises(QualityContractError): validate_result(result, inp)


def test_proven_zero_wins_over_separate_context_gap():
    result = validate_case(CASES["weak_with_context_gap"])
    assert result["overall_quality"] == "weak" and result["insufficient_context"]["present"]


def test_validator_does_not_normalize_evidence_or_mutate_inputs():
    result, inp = base()
    original = copy.deepcopy(result)
    returned = validate_result(result, inp)
    returned["scores"]["progression"] = 0
    assert result == original
    result["quality_flags"] = [{"flag_id": "Q04_LOW_PROGRESSION", "evidence": "прозвучало раньше твоего выбора"}]
    result["scores"]["progression"] = 0
    result["overall_quality"] = "weak"
    failed = copy.deepcopy(result)
    # Add ё to the supplied quote; neither spelling nor case is normalized.
    result["quality_flags"][0]["evidence"] = "прозвучало раньшё твоего выбора"
    untouched = copy.deepcopy(result)
    with pytest.raises(QualityContractError): validate_result(result, inp)
    assert result == untouched
    assert validate_result(failed, inp)["quality_flags"] == failed["quality_flags"]


@pytest.mark.parametrize("field,value", [("schema_version", "2.0"), ("schema_version", 1), ("language", "en"),
                                        ("synthetic", False), ("provenance", "direct_olga_confirmed"),
                                        ("specification", "knowledge/evaluation/метод_Ольги_оценка.md"), ("cases", [])])
def test_corpus_envelope_validation(field, value):
    corpus = copy.deepcopy(CORPUS)
    corpus[field] = value
    with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
        path = Path(directory) / "quality.json"
        path.write_text(json.dumps(corpus, ensure_ascii=False))
        with pytest.raises(QualityContractError): load_corpus(path)


def test_corpus_unknown_fields_and_duplicate_ids_rejected():
    for change in ("extra", "duplicate"):
        corpus = copy.deepcopy(CORPUS)
        if change == "extra": corpus["extra"] = True
        else: corpus["cases"].append(copy.deepcopy(corpus["cases"][0]))
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            path = Path(directory) / "quality.json"
            path.write_text(json.dumps(corpus))
            with pytest.raises(QualityContractError): load_corpus(path)


def test_corpus_path_cannot_escape_tests():
    with pytest.raises(QualityContractError): load_corpus("/etc/passwd")
    with pytest.raises(QualityContractError): load_corpus("tests/../tests/response_quality_evaluator_cases.json")


def test_prompt_preserves_context_and_excludes_gold():
    builder = QualityPromptBuilder()
    case = CASES["formulaic_multiple_turns"]
    messages = builder.build(case["input"])
    envelope = json.loads(messages[1]["content"].split("\n", 1)[1])
    assert envelope == case["input"]
    assert "не коуч" in messages[0]["content"]
    assert "не переписывай" in messages[0]["content"]
    assert "не возвращай HF-коды" in messages[0]["content"]
    assert case["expected"]["reason"] not in messages[0]["content"] + messages[1]["content"]
    with pytest.raises(QualityContractError): builder.build({**case["input"], "expected": case["expected"]})


def test_fresh_conversation_not_automatically_insufficient():
    result = validate_case(CASES["dont_know_space"])
    assert result["overall_quality"] == "strong" and not result["insufficient_context"]["present"]


def test_quality_modules_have_no_methodology_gold_runtime_or_network_imports():
    for path in (ROOT / "services/quality_evaluation").glob("*.py"):
        source = path.read_text()
        imports = [node for node in ast.walk(ast.parse(source)) if isinstance(node, (ast.Import, ast.ImportFrom))]
        names = [node.module or "" for node in imports if isinstance(node, ast.ImportFrom)]
        names += [alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names]
        # Runtime may reuse only the explicitly authorized DEV identity guard.
        if path.name == "runtime.py":
            method_imports = [node for node in imports if isinstance(node, ast.ImportFrom)
                              and (node.module or "").startswith("services.evaluation")]
            assert len(method_imports) == 1
            assert method_imports[0].module == "services.evaluation.runtime"
            assert [alias.name for alias in method_imports[0].names] == ["is_dev_runtime"]
            names.remove("services.evaluation.runtime")
        assert not any(name.startswith(("services.evaluation", "openai", "urllib", "socket", "bot", "handlers")) for name in names)
        assert "coaching_evaluator_cases.json" not in source and "expected_result" not in source


def test_offline_runner_success_and_failure(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("quality_runner", ROOT / "tests/run_response_quality_cases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
    assert "22/22" in capsys.readouterr().out
    def invalid(): raise QualityContractError("Synthetic invalid envelope")
    monkeypatch.setattr(module, "load_corpus", invalid)
    assert module.main() == 1
    assert "FAIL" in capsys.readouterr().out


@pytest.mark.parametrize("location,key", [("flag", "evidence"), ("flag", "flag_id"),
                                        ("gap", "present"), ("gap", "items"),
                                        ("scores", "naturalness")])
def test_required_nested_fields_rejected(location, key):
    case = CASES["generic_paraphrase"]
    result, inp = copy.deepcopy(case["expected"]), case["input"]
    target = result["quality_flags"][0] if location == "flag" else result["insufficient_context"] if location == "gap" else result["scores"]
    del target[key]
    with pytest.raises(QualityContractError): validate_result(result, inp)


def test_context_and_pattern_input_are_typed_and_empty_context_content_is_allowed():
    _, inp = base()
    inp["conversation_context"] = [{"role": "user", "content": ""}]
    assert validate_input(inp) == inp
    inp["conversation_context"][0]["content"] = None
    with pytest.raises(QualityContractError): validate_input(inp)
    _, inp = base()
    inp["recent_assistant_response_patterns"] = [None]
    with pytest.raises(QualityContractError): validate_input(inp)


def test_non_boolean_context_flag_rejected():
    result, inp = base()
    result["insufficient_context"]["present"] = 0
    with pytest.raises(QualityContractError): validate_result(result, inp)


def test_duplicate_json_keys_and_nonstandard_constants_rejected():
    for text in ('{"schema_version":"1.0","schema_version":"1.0"}', '{"schema_version":NaN}'):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            path = Path(directory) / "quality.json"
            path.write_text(text)
            with pytest.raises(QualityContractError): load_corpus(path)
