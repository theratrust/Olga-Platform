"""Separate contract validity, semantic label agreement, and full JSON equality."""

from .contract import RULE_IDS

SEMANTIC_LABELS = ("hard_fail", "overall", "decision", "insufficient_context", "hf_rules")


def qualification_outcome(contract_valid, comparison):
    """Classify only validated results; retain infrastructure subtypes separately."""
    if not contract_valid:
        return "INFRA_FAIL"
    matches = comparison["matches"]
    if any(not matches[key] for key in SEMANTIC_LABELS):
        return "SEMANTIC_MISMATCH"
    return "EXACT_MATCH" if matches["full_result"] else "SEMANTIC_PASS_DETAIL_VARIANCE"


def compare_results(actual, expected):
    actual_rules = {v["rule_id"] for v in actual["violations"]}
    expected_rules = {v["rule_id"] for v in expected["violations"]}
    matches = {key: actual[key] == expected[key] for key in ("hard_fail", "overall", "decision")}
    matches["insufficient_context"] = actual["insufficient_context"]["present"] == expected["insufficient_context"]["present"]
    matches["hf_rules"] = actual_rules == expected_rules
    matches["full_result"] = actual == expected
    return {"matches": matches, "mismatched_fields": [key for key, value in matches.items() if not value],
            "missing_hf_rules": sorted(expected_rules - actual_rules),
            "extra_hf_rules": sorted(actual_rules - expected_rules),
            "different_result_fields": sorted(key for key in expected if actual[key] != expected[key])}


def calculate_metrics(records, elapsed_seconds):
    count = len(records)
    valid = [record for record in records if record["contract_valid"]]
    def rate(numerator, denominator):
        return numerator / denominator if denominator else None
    metrics = {"attempted_cases": count, "contract_valid_cases": len(valid),
               "contract_valid_response_rate": rate(len(valid), count),
               "total_elapsed_seconds": elapsed_seconds,
               "infrastructure_failures": count - len(valid)}
    for key in ("hard_fail", "overall", "decision", "insufficient_context", "full_result"):
        correct = sum(record["comparison"]["matches"][key] for record in valid)
        name = "exact_full_result_match_rate" if key == "full_result" else key + "_agreement"
        # Invalid responses count as non-agreement for these attempted-case rates.
        metrics[name] = rate(correct, count)
    per_rule = {}
    for rule in sorted(RULE_IDS):
        tp = fp = fn = 0
        for record in valid:
            predicted = {v["rule_id"] for v in record["validated_result"]["violations"]}
            expected = {v["rule_id"] for v in record["expected_result"]["violations"]}
            tp += rule in predicted and rule in expected
            fp += rule in predicted and rule not in expected
            fn += rule not in predicted and rule in expected
        per_rule[rule] = {"tp": tp, "fp": fp, "fn": fn,
                          "precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn)}
    tp = sum(row["tp"] for row in per_rule.values())
    fp = sum(row["fp"] for row in per_rule.values())
    fn = sum(row["fn"] for row in per_rule.values())
    metrics.update(hf_rule_precision=rate(tp, tp + fp), hf_rule_recall=rate(tp, tp + fn),
                   per_rule=per_rule, hf_metric_cases=len(valid), hf_metric_excluded_cases=count-len(valid),
                   semantic_label_mismatch_cases=sum(any(not record["comparison"]["matches"][key]
                       for key in SEMANTIC_LABELS) for record in valid),
                   latency_seconds_by_case={record["case_id"]: record["latency_seconds"] for record in records})
    outcomes = [qualification_outcome(record["contract_valid"], record.get("comparison"))
                for record in records]
    metrics.update(semantic_label_mismatches=outcomes.count("SEMANTIC_MISMATCH"),
                   semantic_pass_detail_variance=outcomes.count("SEMANTIC_PASS_DETAIL_VARIANCE"),
                   exact_matches=outcomes.count("EXACT_MATCH"))
    first_valid = sum(record.get("first_attempt", record)["contract_valid"] for record in records)
    retried = sum(record.get("retry_attempt") is not None for record in records)
    recovered = sum(bool(record.get("recovered")) for record in records)
    metrics.update(first_pass_contract_valid_cases=first_valid,
                   first_pass_contract_valid_rate=rate(first_valid, count),
                   first_pass_infrastructure_failures=count-first_valid,
                   retry_attempted_cases=retried, retry_recovered_cases=recovered,
                   retry_recovery_rate=rate(recovered, retried),
                   final_contract_valid_cases=len(valid),
                   final_contract_valid_rate=rate(len(valid), count),
                   final_infrastructure_failures=count-len(valid))
    return metrics
