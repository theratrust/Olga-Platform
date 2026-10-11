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

def fixture_data():
    data = json.loads(CASES_PATH.read_text())
    assert data["schema_version"] == 1
    return data

def cases():
    return fixture_data()["cases"]

def model_input(case):
    """The fields used for generator history; illustrative moves are excluded."""
    return (json.dumps(case["context"], ensure_ascii=False, sort_keys=True),
            case["latest_user"])

def test_fixture_structure_and_source_links():
    items = cases()
    assert len(items) == 27
    assert len({item["id"] for item in items}) == len(items)
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

def test_pair_metadata_and_actual_generator_inputs():
    data = fixture_data()
    items = data["cases"]
    by_id = {item["id"]: item for item in items}
    metadata = data["pair_metadata"]
    assert len(metadata) == 13
    assert len({entry["pair_id"] for entry in metadata}) == len(metadata)
    assert len({model_input(item) for item in items}) == len(items)
    assert Counter(item["pair_id"] for item in items) == Counter({
        entry["pair_id"]: len(entry["member_ids"]) for entry in metadata
    })
    seen_member_ids = []
    for entry in metadata:
        members = [by_id[member_id] for member_id in entry["member_ids"]]
        seen_member_ids.extend(entry["member_ids"])
        assert all(item["pair_id"] == entry["pair_id"] for item in members)
        assert entry["source_ids"]
        assert entry["variable"].strip() and entry["expected_behavior_difference"].strip()
        assert entry["exact_latest_user_inputs"] == [item["latest_user"] for item in members]
        if entry["group_type"] == "pair":
            assert len(members) == 2
            assert members[0]["context"] == members[1]["context"]
            assert members[0]["latest_user"] != members[1]["latest_user"]
            assert model_input(members[0]) != model_input(members[1])
        else:
            assert entry["group_type"] == "triple"
            assert entry["pair_id"] == "uncertainty"
            assert len(members) == 3
            assert len({model_input(item) for item in members}) == 3
    assert len(seen_member_ids) == len(set(seen_member_ids)) == len(items)

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
    by_id = {item["id"]: item for item in items}
    uncertainty = [item for item in items if item["hard_guard"] == "ya_ne_znayu"]
    assert len(uncertainty) == 3
    assert all(
        item["classification"] == "HYPOTHESIS_PROHIBITED"
        and not item["new_assistant_hypothesis_allowed"]
        and "O-M06" in item["source_ids"]
        and "не знаю" in item["latest_user"].lower()
        for item in uncertainty
    )
    rejected = by_id["rejection_active"]
    reopened = by_id["rejection_user_reopens"]
    assert rejected["hard_guard"] == "rejected"
    assert rejected["classification"] == "HYPOTHESIS_PROHIBITED"
    assert "O-AI05" in rejected["source_ids"]
    assert reopened["classification"] == "REFLECTION_SAFE"
    assert reopened["context"] == rejected["context"]
    assert [turn["role"] for turn in rejected["context"]] == ["assistant", "user"]
    assert "одиночеств" in rejected["context"][1]["content"].lower()
    assert "одиночеств" in reopened["latest_user"].lower()
    assert rejected["latest_user"] != reopened["latest_user"]

def test_reflection_partner_work_and_tentative_contrasts():
    by_id = {item["id"]: item for item in cases()}
    assert by_id["loneliness_authored"]["move_type"] == "USER_AUTHORED_REFLECTION"
    assert by_id["loneliness_invented"]["classification"] == "HYPOTHESIS_PROHIBITED"
    assert by_id["fear_plain"]["classification"] == "REFLECTION_SAFE"
    assert by_id["fear_tentative"]["classification"] == "HYPOTHESIS_PROHIBITED"
    assert "боюсь перемен" in by_id["fear_plain"]["latest_user"]
    assert "боюсь перемен" not in by_id["fear_tentative"]["latest_user"]
    assert "муж решает за меня" in by_id["partner_blame"]["latest_user"]
    assert "муж решает за меня" not in by_id["partner_neutral"]["latest_user"]
    assert "хочу выйти на работу" in by_id["work_user_authored"]["latest_user"]
    assert "работу я пока не хочу" in by_id["work_solution"]["latest_user"]
