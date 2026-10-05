"""Independent quality agreement, taxonomy and structural reliability metrics."""
from collections import Counter
from .contract import DIMENSIONS, FLAG_DIMENSIONS

OUTCOMES = (
    "EXACT_MATCH", "QUALITY_MATCH_DETAIL_VARIANCE", "OVERALL_MATCH_SCORE_VARIANCE",
    "OVERALL_MATCH_FLAG_VARIANCE", "OVERALL_MATCH_SCORE_AND_FLAG_VARIANCE",
    "QUALITY_SEMANTIC_MISMATCH", "INFRA_FAIL",
)
OVERALL_LABELS = ("strong", "acceptable", "weak", "insufficient_context")


def compare_results(actual, expected):
    predicted = {flag["flag_id"] for flag in actual["quality_flags"]}
    gold = {flag["flag_id"] for flag in expected["quality_flags"]}
    return {"overall_quality": actual["overall_quality"] == expected["overall_quality"],
            "scores": actual["scores"] == expected["scores"], "flags": predicted == gold,
            "full_result": actual == expected,
            "dimension_matches": {dim: actual["scores"][dim] == expected["scores"][dim] for dim in DIMENSIONS},
            "missing_flags": sorted(gold - predicted), "extra_flags": sorted(predicted - gold)}


def qualification_outcome(contract_valid, comparison):
    if not contract_valid:
        return "INFRA_FAIL"
    if not comparison["overall_quality"]:
        return "QUALITY_SEMANTIC_MISMATCH"
    if not comparison["scores"] and not comparison["flags"]:
        return "OVERALL_MATCH_SCORE_AND_FLAG_VARIANCE"
    if not comparison["scores"]:
        return "OVERALL_MATCH_SCORE_VARIANCE"
    if not comparison["flags"]:
        return "OVERALL_MATCH_FLAG_VARIANCE"
    return "EXACT_MATCH" if comparison["full_result"] else "QUALITY_MATCH_DETAIL_VARIANCE"


def rate(n, d):
    return n / d if d else None


def matrix(labels):
    return {label: {pred: 0 for pred in labels} for label in labels}


def calculate_metrics(records, elapsed_seconds):
    count = len(records)
    valid = [r for r in records if r["contract_valid"]]
    first = sum(r["first_attempt"]["contract_valid"] for r in records)
    retried = sum(r["retry_attempt"] is not None for r in records)
    recovered = sum(r["recovered"] for r in records)
    overall = matrix(OVERALL_LABELS)
    dimensions = {dim: {"agreement_count": 0, "confusion_matrix": matrix(("0", "1", "2", "null"))} for dim in DIMENSIONS}
    flags = {flag: {"tp": 0, "fp": 0, "fn": 0} for flag in FLAG_DIMENSIONS}
    for r in valid:
        actual, expected = r["validated_result"], r["quality_gold_result"]
        overall[expected["overall_quality"]][actual["overall_quality"]] += 1
        for dim in DIMENSIONS:
            a, e = actual["scores"][dim], expected["scores"][dim]
            dimensions[dim]["agreement_count"] += a == e
            dimensions[dim]["confusion_matrix"]["null" if e is None else str(e)]["null" if a is None else str(a)] += 1
        a = {f["flag_id"] for f in actual["quality_flags"]}
        e = {f["flag_id"] for f in expected["quality_flags"]}
        for flag, row in flags.items():
            row["tp"] += flag in a and flag in e
            row["fp"] += flag in a and flag not in e
            row["fn"] += flag not in a and flag in e
    for row in dimensions.values():
        row["agreement_rate"] = rate(row["agreement_count"], count)
    for row in flags.values():
        row["precision"] = rate(row["tp"], row["tp"] + row["fp"])
        row["recall"] = rate(row["tp"], row["tp"] + row["fn"])
    agreement = sum(r["comparison"]["overall_quality"] for r in valid)
    exact = sum(r["comparison"]["full_result"] for r in valid)
    counts = Counter(r["outcome"] for r in records)
    return {"attempted_cases": count, "first_pass_contract_valid_cases": first,
            "first_pass_contract_valid_rate": rate(first, count), "first_pass_infrastructure_failures": count-first,
            "retry_attempted_cases": retried, "retry_recovered_cases": recovered,
            "retry_recovery_rate": rate(recovered, retried),
            "final_contract_valid_cases": len(valid), "final_contract_valid_rate": rate(len(valid), count),
            "final_infrastructure_failures": count-len(valid),
            "overall_quality_agreement_count": agreement, "overall_quality_agreement_rate": rate(agreement, count),
            "overall_quality_confusion_matrix": overall, "dimensions": dimensions, "quality_flags": flags,
            "semantic_metric_cases": len(valid), "semantic_metric_excluded_cases": count-len(valid),
            "exact_full_result_match_count": exact, "exact_full_result_match_rate": rate(exact, count),
            "outcome_counts": {label: counts[label] for label in OUTCOMES},
            "latency_seconds_by_case": {r["case_id"]: r["latency_seconds"] for r in records},
            "total_elapsed_seconds": elapsed_seconds}
