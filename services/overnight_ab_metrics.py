"""Deterministic descriptive soak analysis, never a runtime evaluator verdict."""
import math
import re
from collections import Counter, defaultdict
from .conversation_benchmark_metrics import calculate_metrics, latency_stats, rate

def validate_candidate_id(candidate_id):
    if type(candidate_id)is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}",candidate_id) is None or candidate_id=="BASELINE":
        raise ValueError("Invalid candidate identity")
    return candidate_id


def wilson(n,d):
    if not d:return None
    z=1.959963984540054;p=n/d;den=1+z*z/d
    center=(p+z*z/(2*d))/den
    half=z*math.sqrt(p*(1-p)/d+z*z/(4*d*d))/den
    return [max(0,center-half),min(1,center+half)]


def distribution(values):
    values=[v for v in values if type(v)is int and v>=0]
    return {"observed":len(values),"counts":dict(sorted(Counter(values).items())),
            "mean":sum(values)/len(values) if values else None,
            "minimum":min(values) if values else None,"maximum":max(values) if values else None}


def reconstruct(events):
    groups={};attempts={}
    for e in events:
        if e["event"] not in {"generator_attempt","evaluators","scenario_end"}:continue
        key=(e["trial"],e["variant"],e["scenario_id"])
        if key not in groups:
            groups[key]={"scenario_id":str(e["trial"])+":"+e["scenario_id"],"planned_turns":6,"completed":False,"turns":[]}
        s=groups[key]
        if e["event"]=="generator_attempt":
            t={"turn_number":e["turn"],"generator":{"success":e["success"],"error_kind":e["failure_kind"],"latency_ms":e["diagnostic"]["latency_ms"] or 0},
               "methodology":None,"quality":None}
            s["turns"].append(t);attempts[key+(e["turn"],)]=t
        elif e["event"]=="evaluators":
            t=attempts[key+(e["turn"],)];t.update(methodology=e["methodology"],quality=e["quality"])
        else:s["completed"]=e["completed"]
    return groups


def generator_metrics(events):
    n=len(events);fail=sum(not e["success"] for e in events)
    empty=sum(e["failure_kind"]=="empty_response" for e in events)
    def breakdown(field):
        counts=defaultdict(lambda:[0,0])
        for e in events:counts[str(e[field])][0]+=1;counts[str(e[field])][1]+=not e["success"]
        return {k:{"attempts":a,"failures":f,"failure_rate":rate(f,a)} for k,(a,f) in sorted(counts.items())}
    return {"attempts":n,"successful_calls":n-fail,"failures":fail,"failure_rate":rate(fail,n),
            "empty_response_count":empty,"empty_response_rate":rate(empty,n),"failure_proportion_wilson_95":wilson(fail,n),
            "failure_classifications":dict(sorted(Counter(e["failure_classification"] for e in events if not e["success"]).items())),
            "finish_reason_distribution":dict(sorted(Counter(e["diagnostic"]["finish_reason"] or "unavailable" for e in events).items())),
            "reasoning_present_rate":rate(sum(e["diagnostic"]["reasoning_present"] for e in events),n),
            "reasoning_present_final_empty":sum(e["diagnostic"]["reasoning_present"] and e["failure_kind"]=="empty_response" for e in events),
            "finish_reason_length_count":sum(e["diagnostic"]["finish_reason"]=="length" for e in events),
            "completion_token_distribution":distribution([e["diagnostic"]["completion_tokens"] for e in events]),
            "reasoning_token_distribution":distribution([e["diagnostic"]["reasoning_tokens"] for e in events]),
            "latency":latency_stats([e["diagnostic"]["latency_ms"] for e in events]),
            "by_scenario":breakdown("scenario_id"),"by_turn":breakdown("turn"),"by_trial":breakdown("trial")}


def paired_metrics(events,candidate_id="CANDIDATE_A"):
    validate_candidate_id(candidate_id)
    generated={(e["trial"],e["variant"],e["scenario_id"],e["turn"]):e["success"] for e in events if e["event"]=="generator_attempt"}
    evaluations={(e["trial"],e["variant"],e["scenario_id"],e["turn"]):e for e in events if e["event"]=="evaluators"}
    pairs=[]
    for (trial,variant,sid,turn),a in evaluations.items():
        if variant!="BASELINE":continue
        bkey=(trial,candidate_id,sid,turn);akey=(trial,variant,sid,turn)
        b=evaluations.get(bkey)
        if b and generated.get(akey) and generated.get(bkey) and a["quality"]["final_contract_valid"] and b["quality"]["final_contract_valid"]:
            pairs.append((a,b))
    results={}
    rank={"weak":0,"acceptable":1,"strong":2}
    for field in ["non_repetition","progression","question_quality","Q02_UNNECESSARY_PARAPHRASE","Q03_REPETITIVE_STRUCTURE","Q05_GENERIC_QUESTION","overall_quality"]:
        deltas=[]
        for a,b in pairs:
            qa,qb=a["quality"],b["quality"]
            if field.startswith("Q"):
                x,y=int(field in qa["quality_flags"]),int(field in qb["quality_flags"])
            elif field=="overall_quality":x,y=rank.get(qa[field]),rank.get(qb[field])
            else:x,y=qa["scores"][field],qb["scores"][field]
            if x is not None and y is not None:deltas.append(y-x)
        bad_sign=1 if field.startswith("Q") else -1
        results[field]={"comparable":len(deltas),"excluded_null_or_insufficient":len(pairs)-len(deltas),
                        "candidate_minus_baseline_mean":sum(deltas)/len(deltas) if deltas else None,
                        "improved":sum(d*bad_sign<0 for d in deltas),"unchanged":sum(d==0 for d in deltas),"worsened":sum(d*bad_sign>0 for d in deltas)}
    # Paired semantic guardrails and primary counts use exactly the same observations.
    def subset(i):
        q=[p[i]["quality"] for p in pairs]
        return {"low_non_repetition":sum(x["scores"]["non_repetition"] is not None and x["scores"]["non_repetition"]<=1 for x in q),
                "low_progression":sum(x["scores"]["progression"] is not None and x["scores"]["progression"]<=1 for x in q),
                **{f:sum(f in x["quality_flags"] for x in q) for f in ("Q02_UNNECESSARY_PARAPHRASE","Q03_REPETITIVE_STRUCTURE","Q07_CONTEXT_MISS","Q08_OVERLONG_OR_UNDERDEVELOPED")},
                "weak":sum(x["overall_quality"]=="weak" for x in q),
                **{d:sum(x["scores"][d] for x in q if x["scores"][d] is not None)/sum(x["scores"][d] is not None for x in q)
                   if any(x["scores"][d] is not None for x in q) else None for d in ("naturalness","contextual_specificity")}}
    return {"quality_pairs":len(pairs),"comparisons":results,"BASELINE":subset(0),candidate_id:subset(1)}


def summarize(events,complete=False,candidate_id="CANDIDATE_A"):
    validate_candidate_id(candidate_id)
    groups=reconstruct(events);result={"variants":{},"paired":paired_metrics(events,candidate_id)}
    for variant in ("BASELINE",candidate_id):
        gens=[e for e in events if e["event"]=="generator_attempt" and e["variant"]==variant]
        scenarios=[s for k,s in groups.items() if k[1]==variant]
        m=calculate_metrics(scenarios)
        methods=m["methodology"];methods["pass_rate"]=rate(methods["overall_counts"]["pass"],methods["valid_turns"])
        methods["accept_rate"]=rate(methods["decision_counts"]["accept"],methods["valid_turns"])
        q=m["quality"];q["flag_rates"]={k:rate(n,q["valid_turns"]) for k,n in q["flag_frequencies"].items()}
        q["repeated_scenario_trials"]=len({sid for w in q["weakness_analysis"].values() for sid in w["repeated_within_scenario"]})
        q["consecutive_q03_completed_scenario_trials"]=calculate_metrics([s for s in scenarios if s["completed"]])["quality"]["consecutive_q03_pairs"]
        result["variants"][variant]={"generator":generator_metrics(gens),"coaching":m,"completed_scenario_trials":sum(s["completed"] for s in scenarios)}
    a=result["variants"]["BASELINE"]["generator"];b=result["variants"][candidate_id]["generator"]
    ar,br=a["failure_rate"],b["failure_rate"];diff=br-ar if ar is not None and br is not None else None
    ci_a,ci_b=a["failure_proportion_wilson_95"],b["failure_proportion_wilson_95"]
    result["reliability_comparison"]={"candidate_minus_baseline_failure_rate":diff,"relative_risk":br/ar if ar else None,
        "difference_95_wilson_bound_estimate":[ci_b[0]-ci_a[1],ci_b[1]-ci_a[0]] if ci_a and ci_b else None,
        "caution":"Call-level descriptive intervals ignore within-scenario/trial dependence; no significance claim."}
    reliability="RELIABILITY_INCONCLUSIVE"
    if complete and min(a["attempts"],b["attempts"])>=100 and diff is not None:
        if abs(diff)<.02:reliability=f"{candidate_id}_RELIABILITY_SIMILAR"
        elif a["failures"]+b["failures"]>=10 and diff>=.05 and (ar==0 or br/ar>=1.5):reliability=f"{candidate_id}_RELIABILITY_WORSE"
        elif a["failures"]+b["failures"]>=10 and diff<=-.05 and ar and br/ar<=2/3:reliability=f"{candidate_id}_RELIABILITY_BETTER"
    quality="QUALITY_INCONCLUSIVE";p=result["paired"];x,y=p["BASELINE"],p[candidate_id]
    reductions={k:(x[k]-y[k])/x[k] if x[k] else None for k in ["low_non_repetition","low_progression","Q02_UNNECESSARY_PARAPHRASE","Q03_REPETITIVE_STRUCTURE"]}
    improvements=sum(reductions[k] is not None and reductions[k]>=threshold for k,threshold in [("low_non_repetition",.25),("low_progression",.2),("Q02_UNNECESSARY_PARAPHRASE",.25),("Q03_REPETITIVE_STRUCTURE",.25)])
    ca=result["variants"][candidate_id]["coaching"]["methodology"]
    guard=ca["hard_fail_count"]==0 and ca["overall_counts"]["pass"]==ca["valid_turns"]==ca["decision_counts"]["accept"]
    guard=guard and all(y[k]<=x[k] for k in ["weak","Q07_CONTEXT_MISS","Q08_OVERLONG_OR_UNDERDEVELOPED"])
    guard=guard and all(x[k] is not None and y[k] is not None and y[k]>=x[k]-.1 for k in ["naturalness","contextual_specificity"])
    if complete and p["quality_pairs"]>=30:
        if ca["hard_fail_count"]:quality=f"{candidate_id}_QUALITY_WORSE"
        elif improvements>=2 and guard:quality=f"{candidate_id}_QUALITY_BETTER"
        elif sum(y[k]>x[k] for k in reductions)>=2 and improvements==0:quality=f"{candidate_id}_QUALITY_WORSE"
        else:quality=f"{candidate_id}_QUALITY_MIXED"
    result["decision"]={"generator_reliability":reliability,"coaching_quality":quality,
                        "paired_primary_relative_reductions":reductions,"material_targets_improved":improvements,"quality_guardrails_pass":guard}
    return result
