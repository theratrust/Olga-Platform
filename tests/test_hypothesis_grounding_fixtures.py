"""Structural checks for synthetic, source-linked hypothesis-grounding cases."""
import json
from collections import Counter
from pathlib import Path

CASES_PATH = Path(__file__).parent / "fixtures" / "hypothesis_grounding_cases.json"
CLASSES = {
    "REFLECTION_SAFE", "HYPOTHESIS_ALLOWED", "HYPOTHESIS_OPTIONAL",
    "HYPOTHESIS_AVOID", "HYPOTHESIS_PROHIBITED",
}
MOVES = {
    "USER_AUTHORED_REFLECTION", "GROUNDED_TENTATIVE_HYPOTHESIS",
    "UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS", "UNSUPPORTED_CAUSAL_HYPOTHESIS",
    "CANDIDATE_ANSWER_DISGUISED_AS_QUESTION", "NEUTRAL_CLARIFICATION",
}

def cases():
    data = json.loads(CASES_PATH.read_text())
    assert data["schema_version"] == 1
    return data["cases"]

def test_fixture_structure_and_source_links():
    items = cases()
    assert len(items) >= 20
    assert len({item["id"] for item in items}) == len(items)
    assert len({item["pair_id"] for item in items}) >= 5
    for item in items:
        assert item["classification"] in CLASSES
        assert item["move_type"] in MOVES
        assert item["latest_user"].strip()
        assert item["illustrative_assistant_move"].strip()
        assert item["rationale"].strip()
        assert item["source_ids"] and all(
            source.startswith(("O-M", "O-AI")) for source in item["source_ids"]
        )
        assert item["user_authored_content"] and item["invented_content"]
        assert item["acceptable"] and item["unacceptable"]
        assert type(item["new_assistant_hypothesis_allowed"]) is bool
        assert type(item["tentative_wording_alone_changes_acceptability"]) is bool
        assert all(
            turn["role"] in {"user", "assistant"} and turn["content"].strip()
            for turn in item["context"]
        )

def test_grounded_hypothesis_is_optional_not_required():
    items = cases()
    assert any(item["classification"] == "HYPOTHESIS_OPTIONAL" for item in items)
    assert all(
        item["classification"] == "HYPOTHESIS_OPTIONAL"
        for item in items if item["new_assistant_hypothesis_allowed"]
    )
    assert all(
        not item["tentative_wording_alone_changes_acceptability"] for item in items
    )

def test_uncertainty_and_rejection_guards():
    items = cases()
    uncertainty = [item for item in items if item["hard_guard"] == "ya_ne_znayu"]
    assert len(uncertainty) >= 3
    assert all(
        item["classification"] == "HYPOTHESIS_PROHIBITED"
        and not item["new_assistant_hypothesis_allowed"]
        and "O-M06" in item["source_ids"]
        for item in uncertainty
    )
    rejected = [item for item in items if item["hard_guard"] == "rejected"]
    assert rejected
    assert all(
        item["classification"] == "HYPOTHESIS_PROHIBITED"
        and "O-AI05" in item["source_ids"]
        for item in rejected
    )

def test_reflection_and_contrastive_coverage():
    items = cases()
    by_id = {item["id"]: item for item in items}
    assert by_id["loneliness_authored"]["move_type"] == "USER_AUTHORED_REFLECTION"
    assert by_id["loneliness_invented"]["classification"] == "HYPOTHESIS_PROHIBITED"
    assert by_id["rejection_user_reopens"]["classification"] == "REFLECTION_SAFE"
    assert by_id["fear_plain"]["classification"] == by_id["fear_tentative"]["classification"]
    assert by_id["fear_plain"]["latest_user"] == by_id["fear_tentative"]["latest_user"]
    counts = Counter(item["pair_id"] for item in items)
    assert counts["partner"] >= 2 and counts["work"] >= 2
    assert all(count >= 2 for count in counts.values())
