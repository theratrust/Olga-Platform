"""Descriptive conversation evidence metrics, never gold judgments or routing."""
import math
import statistics
from collections import Counter
from services.quality_evaluation.contract import DIMENSIONS, FLAG_DIMENSIONS


def rate(n, d):
    return n / d if d else None


def latency_stats(values):
    values = sorted(v for v in values if type(v) in (int, float) and math.isfinite(v) and v >= 0)
    return {"count": len(values), "mean_ms": statistics.mean(values) if values else None,
            "median_ms": statistics.median(values) if values else None,
            "p95_ms": values[math.ceil(.95 * len(values)) - 1] if values else None}


def reliability(records):
    first = sum(r["first_pass_contract_valid"] for r in records)
    valid = sum(r["final_contract_valid"] for r in records)
    retried = sum(r["retry_attempted"] for r in records)
    recovered = sum(r["retry_recovered"] for r in records)
    return {"attempted": len(records), "first_pass_valid": first, "first_pass_valid_rate": rate(first, len(records)),
            "retry_attempted": retried, "retry_recovered": recovered, "retry_recovery_rate": rate(recovered, retried),
            "final_valid": valid, "final_valid_rate": rate(valid, len(records)), "failures": len(records)-valid}


def calculate_metrics(scenarios):
    turns = [t for s in scenarios for t in s["turns"]]
    methods = [t["methodology"] for t in turns if t["methodology"] is not None]
    qualities = [t["quality"] for t in turns if t["quality"] is not None]
    valid_m = [m for m in methods if m["final_contract_valid"]]
    valid_q = [q for q in qualities if q["final_contract_valid"]]
    def frequencies(records, field, labels):
        counts = Counter(r[field] for r in records)
        return {label: counts[label] for label in labels}
    hf = {f"HF{i:02d}": sum(f"HF{i:02d}" in m["hf_ids"] for m in valid_m) for i in range(1,9)}
    qflags = {flag: sum(flag in q["quality_flags"] for q in valid_q) for flag in FLAG_DIMENSIONS}
    distributions = {dim: {str(v) if v is not None else "null": sum(q["scores"][dim] == v for q in valid_q)
                           for v in (0,1,2,None)} for dim in DIMENSIONS}
    low = {dim: sum(q["scores"][dim] is not None and q["scores"][dim] <= 1 for q in valid_q) for dim in DIMENSIONS}
    per_scenario = []
    signals = {"dimension:"+dim: {} for dim in DIMENSIONS}
    signals.update({"flag:"+flag: {} for flag in FLAG_DIMENSIONS})
    rank = {"strong": 2, "acceptable": 1, "weak": 0}
    for scenario in scenarios:
        valid = [t for t in scenario["turns"] if t["quality"] and t["quality"]["final_contract_valid"]]
        lows = {dim: sum(t["quality"]["scores"][dim] is not None and t["quality"]["scores"][dim] <= 1 for t in valid) for dim in DIMENSIONS}
        q03 = [t["turn_number"] for t in valid if "Q03_REPETITIVE_STRUCTURE" in t["quality"]["quality_flags"]]
        pairs = sum(b == a+1 for a,b in zip(q03, q03[1:]))
        # Late-vs-early halves use original scripted positions and comparable labels.
        midpoint = scenario["planned_turns"] // 2
        early = [rank[t["quality"]["overall_quality"]] for t in valid if t["turn_number"] <= midpoint and t["quality"]["overall_quality"] in rank]
        late = [rank[t["quality"]["overall_quality"]] for t in valid if t["turn_number"] > midpoint and t["quality"]["overall_quality"] in rank]
        deterioration = statistics.mean(late) < statistics.mean(early) if early and late else None
        first, last = scenario["turns"][0]["quality"] if scenario["turns"] else None, scenario["turns"][-1]["quality"] if scenario["turns"] else None
        endpoints = (rank[last["overall_quality"]] < rank[first["overall_quality"]]
                     if scenario["completed"] and first and last and first["final_contract_valid"] and last["final_contract_valid"]
                     and first["overall_quality"] in rank and last["overall_quality"] in rank else None)
        row = {"scenario_id": scenario["scenario_id"], "dimension_le_1_counts": lows, "q03_turns": q03,
               "consecutive_q03_pairs": pairs, "late_mean_lower_than_early": deterioration,
               "last_overall_worse_than_first": endpoints,
               "early_comparable_turns": len(early), "late_comparable_turns": len(late)}
        per_scenario.append(row)
        for dim, count in lows.items():
            if count:
                signals["dimension:"+dim][scenario["scenario_id"]] = count
        for flag in FLAG_DIMENSIONS:
            count = sum(flag in t["quality"]["quality_flags"] for t in valid)
            if count:
                signals["flag:"+flag][scenario["scenario_id"]] = count
    weakness = {signal: {"total_occurrences": sum(counts.values()), "scenario_count": len(counts),
                "isolated_within_scenario": [sid for sid,n in counts.items() if n == 1],
                "repeated_within_scenario": [sid for sid,n in counts.items() if n >= 2],
                "recurring_cross_scenario": len(counts) >= 2} for signal,counts in signals.items() if counts}
    hard = sum(m["hard_fail"] for m in valid_m)
    return {"planned_turns": sum(s["planned_turns"] for s in scenarios), "generator_attempted_turns": len(turns),
            "generated_turns": sum(t["generator"]["success"] for t in turns),
            "skipped_turns_after_generator_failure": sum(s["planned_turns"]-len(s["turns"]) for s in scenarios),
            "methodology": {"total_turns": len(methods), "valid_turns": len(valid_m), "hard_fail_count": hard,
                "hard_fail_rate": rate(hard, len(valid_m)), "hf_frequencies": hf,
                "overall_counts": frequencies(valid_m, "overall", ("pass","fail","review","insufficient_context")),
                "decision_counts": frequencies(valid_m, "decision", ("accept","retry","escalate","insufficient_context")),
                "reliability": reliability(methods)},
            "quality": {"total_turns": len(qualities), "valid_turns": len(valid_q),
                "overall_counts": frequencies(valid_q, "overall_quality", ("strong","acceptable","weak","insufficient_context")),
                "dimension_distributions": distributions, "flag_frequencies": qflags, "dimension_le_1_counts": low,
                "q03_count": qflags["Q03_REPETITIVE_STRUCTURE"],
                "scenarios_containing_q03": sum(bool(s["q03_turns"]) for s in per_scenario),
                "consecutive_q03_pairs": sum(s["consecutive_q03_pairs"] for s in per_scenario),
                "scenarios_with_non_repetition_le_1_twice": sum(s["dimension_le_1_counts"]["non_repetition"] >= 2 for s in per_scenario),
                "scenarios_with_progression_le_1_twice": sum(s["dimension_le_1_counts"]["progression"] >= 2 for s in per_scenario),
                "scenarios_with_late_deterioration": sum(s["late_mean_lower_than_early"] is True for s in per_scenario),
                "per_scenario": per_scenario, "weakness_analysis": weakness, "reliability": reliability(qualities)},
            "infrastructure": {"generator_failures": sum(not t["generator"]["success"] for t in turns),
                "methodology_evaluator_failures": len(methods)-len(valid_m), "quality_evaluator_failures": len(qualities)-len(valid_q),
                "generator_latency": latency_stats([t["generator"]["latency_ms"] for t in turns]),
                "methodology_latency": latency_stats([m["latency_ms"] for m in methods]),
                "quality_latency": latency_stats([q["latency_ms"] for q in qualities])}}
