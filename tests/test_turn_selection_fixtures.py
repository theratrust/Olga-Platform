"""Offline integrity checks for the synthetic turn-selection reference set."""

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "tests/fixtures/turn_selection_cases.json").read_text())
CASES = DATA["cases"]
BY_ID = {case["id"]: case for case in CASES}
SOURCE = (ROOT / "knowledge/method/источник_истины_метода_Ольги.md").read_text()
NOTES = (ROOT / "knowledge/evaluation/turn_selection_fixtures.md").read_text()


def test_schema_and_classification_balance():
    assert DATA["schema_version"] == "1.0"
    assert DATA["synthetic"] is True
    assert DATA["provenance"] == "derived_turn_selection_fixture"
    assert len(CASES) == len(BY_ID) == 20
    assert Counter(case["classification"] for case in CASES) == {
        "QUESTION_USEFUL": 4,
        "QUESTION_OPTIONAL": 9,
        "QUESTION_AVOID": 7,
    }
    for case in CASES:
        assert set(case) in (
            {"id", "context", "latest_user", "classification", "question_allowed",
             "question_required", "question_prohibited", "rationale", "must", "must_not",
             "source_ids"},
            {"id", "context", "latest_user", "classification", "question_allowed",
             "question_required", "question_prohibited", "rationale", "must", "must_not",
             "source_ids", "pair_id"},
        )
        assert case["latest_user"] and case["rationale"]
        assert case["must"] and case["must_not"] and case["source_ids"]
        assert all(t["role"] in {"assistant", "user"} and t["content"] for t in case["context"])
        assert all(f"| {source_id} |" in SOURCE for source_id in case["source_ids"])
        assert f"### `{case['id']}`" in NOTES


def test_question_contract_and_hard_uncertainty():
    for case in CASES:
        assert case["question_required"] is False
        assert not (case["question_required"] and case["question_prohibited"])
        if case["classification"] == "QUESTION_AVOID":
            assert (case["question_allowed"], case["question_prohibited"]) == (False, True)
        else:
            assert (case["question_allowed"], case["question_prohibited"]) == (True, False)
    for case_id in ("uncertainty_plain", "uncertainty_want", "uncertainty_rejects_fear"):
        case = BY_ID[case_id]
        assert case["classification"] == "QUESTION_AVOID"
        assert "O-AI03" in case["source_ids"]
        forbidden = " ".join(case["must_not"]).lower()
        assert "candidate" in forbidden and "option" in forbidden


def test_contrastive_pairs_and_topic_boundaries():
    assert len(DATA["contrastive_pairs"]) == 6
    paired = set()
    for pair in DATA["contrastive_pairs"]:
        assert len(pair["case_ids"]) == 2 and pair["changed_detail"]
        left, right = (BY_ID[case_id] for case_id in pair["case_ids"])
        assert left["pair_id"] == right["pair_id"] == pair["id"]
        assert left["id"] != right["id"]
        paired.update(pair["case_ids"])
    assert len(paired) == 12
    assert BY_ID["hypothesis_still_rejected"]["classification"] == "QUESTION_AVOID"
    assert BY_ID["hypothesis_user_reopens"]["classification"] == "QUESTION_OPTIONAL"
    assert BY_ID["work_excluded"]["classification"] == "QUESTION_AVOID"
    assert BY_ID["partner_not_problem"]["classification"] == "QUESTION_OPTIONAL"
    assert "## Mapping to current evaluator concepts" in NOTES
