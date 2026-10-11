"""Offline integrity checks for the calibrated referent-grounding reference set."""

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "tests/fixtures/referent_grounding_cases.json").read_text())
CASES = DATA["cases"]
BY_ID = {case["id"]: case for case in CASES}
SOURCE = (ROOT / "knowledge/method/источник_истины_метода_Ольги.md").read_text()
NOTES = (ROOT / "knowledge/evaluation/referent_grounding_fixtures.md").read_text()
LABELS = {
    "NATURAL_INFERENCE_ACCEPTABLE",
    "CLARIFICATION_PREFERRED",
    "CLARIFICATION_REQUIRED",
    "UNSUPPORTED_REFERENT_SELECTION",
}


def test_schema_unique_ids_and_source_traceability():
    assert DATA["schema_version"] == "1.0"
    assert DATA["synthetic"] is True
    assert DATA["provenance"] == "derived_referent_grounding_fixture"
    assert len(CASES) == len(BY_ID) == 18
    assert Counter(case["classification"] for case in CASES) == {
        "NATURAL_INFERENCE_ACCEPTABLE": 8,
        "CLARIFICATION_PREFERRED": 5,
        "CLARIFICATION_REQUIRED": 1,
        "UNSUPPORTED_REFERENT_SELECTION": 4,
    }
    for case in CASES:
        assert case["classification"] in LABELS
        assert case["id"] and case["latest_user"] and case["rationale"]
        assert case["context"] and case["acceptable"] and case["unacceptable"]
        assert case["source_ids"]
        assert all(turn["role"] in {"user", "assistant"} and turn["content"]
                   for turn in case["context"])
        assert all(f"| {source_id} |" in SOURCE for source_id in case["source_ids"])
        assert f"`{case['id']}`" in NOTES


def test_classification_flags_are_consistent():
    for case in CASES:
        required = case["clarification_required"]
        neutral = case["neutral_response_acceptable"]
        named = case["naming_explicit_referents_acceptable"]
        assert type(required) is type(neutral) is type(named) is bool
        if case["classification"] == "CLARIFICATION_REQUIRED":
            assert required and not neutral
        else:
            assert not required and neutral
        if case["classification"] == "NATURAL_INFERENCE_ACCEPTABLE":
            assert not required
        assert not (required and case["classification"] == "NATURAL_INFERENCE_ACCEPTABLE")


def test_contrastive_shapes_and_original_recalibration():
    for shape in ("contrast", "sequence", "person", "topic"):
        variants = {case["variant"]: case for case in CASES if case["shape"] == shape}
        assert set(variants) == {
            "RESOLVED", "NATURALLY_INFERABLE", "GENUINELY_AMBIGUOUS"
        }
        assert variants["RESOLVED"]["classification"] == "NATURAL_INFERENCE_ACCEPTABLE"
        assert variants["NATURALLY_INFERABLE"]["classification"] == "NATURAL_INFERENCE_ACCEPTABLE"
        assert variants["GENUINELY_AMBIGUOUS"]["classification"] == "CLARIFICATION_PREFERRED"
    old = {case["id"]: case for case in json.loads(
        (ROOT / "tests/fixtures/turn_selection_cases.json").read_text()
    )["cases"]}
    assert BY_ID["contrast_natural"]["context"] == old["referent_ambiguous"]["context"]
    assert BY_ID["contrast_natural"]["latest_user"] == old["referent_ambiguous"]["latest_user"]
    assert BY_ID["sequence_natural"]["context"] == old["unresolved_referent"]["context"]
    assert BY_ID["sequence_natural"]["latest_user"] == old["unresolved_referent"]["latest_user"]
    assert "superseded for referent-grounding adjudication" in NOTES


def test_uncertainty_rejection_and_named_options_boundaries():
    uncertainty = BY_ID["uncertainty_guard"]
    assert uncertainty["classification"] == "UNSUPPORTED_REFERENT_SELECTION"
    assert "O-AI03" in uncertainty["source_ids"]
    assert "Я не знаю" in uncertainty["latest_user"]
    assert "candidate" in uncertainty["unacceptable"].lower()
    rejection = BY_ID["rejected_hypothesis_guard"]
    assert rejection["classification"] == "UNSUPPORTED_REFERENT_SELECTION"
    assert "O-AI05" in rejection["source_ids"]
    named = BY_ID["named_explicit_options"]
    assert named["naming_explicit_referents_acceptable"]
    assert named["classification"] == "CLARIFICATION_PREFERRED"
    assert "candidate psychological content" in NOTES
    assert "## Later evaluator mapping" in NOTES
