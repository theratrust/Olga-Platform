"""One synthetic DEV scenario, opt-in live generator metadata; no evaluator calls."""
from collections import Counter
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services import coaching_generator
from services.conversation_benchmark import BenchmarkConfig, load_scenarios, select_scenarios
from services.evaluation.runtime import is_dev_runtime


async def diagnose(scenario, config, *, live=False, client=None):
    config.validate()
    if not live:
        return {"dry_run":True,"scenario_id":scenario["id"],"planned_turns":len(scenario["turns"]),
                "network_calls":0,"credential_lookups":0,"artifact_writes":0}
    if not is_dev_runtime(): raise ValueError("DEV identity required")
    key = os.environ.get(config.api_key_env)
    if not key or not key.strip(): raise ValueError("Credentials required")
    owned = client is None
    if owned:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url=config.base_url,api_key=key,timeout=config.timeout)
    attempts = []
    history = []
    instruction = coaching_generator.build_system_instruction(first_name="Тест",archetype=scenario["archetype"])
    try:
        for number,user in enumerate(scenario["turns"],1):
            history.append({"role":"user","content":user})
            metadata = []
            try:
                candidate = await coaching_generator.generate_candidate(client,config.model,
                    coaching_generator.build_messages(instruction,history[-20:]),
                    diagnostic_observer=metadata.append)
                # Exact benchmark classification, not a new generator policy.
                failure = "empty_response" if candidate is None or type(candidate) is str and not candidate.strip() else "response_format_error" if type(candidate) is not str else None
            except Exception:
                failure = "generator_exception"
            attempts.append({"turn_number":number,"failure_kind":failure,
                             "diagnostic":metadata[0] if metadata else {"signals":["diagnostic_unavailable"]}})
            if failure: break
            history.append({"role":"assistant","content":candidate})
    finally:
        if owned: await client.close()
    return {"dry_run":False,"synthetic_only":True,"scenario_id":scenario["id"],
            "planned_turns":len(scenario["turns"]),"attempt_count":len(attempts),
            "completed":len(attempts)==len(scenario["turns"]) and all(a["failure_kind"] is None for a in attempts),
            "failed_attempt_count":sum(a["failure_kind"] is not None for a in attempts),
            "signal_counts":dict(Counter(signal for a in attempts for signal in a["diagnostic"]["signals"])),
            "finish_reason_counts":dict(Counter(a["diagnostic"].get("finish_reason") or "unavailable" for a in attempts)),
            "attempts":attempts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live",action="store_true")
    mode.add_argument("--dry-run",action="store_true")
    parser.add_argument("--scenario-id")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--timeout",type=float,default=60)
    args = parser.parse_args(argv)
    try:
        if args.live and not all((args.scenario_id,args.model,args.base_url,args.api_key_env)):
            raise ValueError("Explicit configuration required")
        scenario = select_scenarios(load_scenarios(),[args.scenario_id or "work_and_autonomy"])[0]
        config = BenchmarkConfig(args.model or "offline-plan",args.base_url or "https://offline.invalid/v1",
                                 args.api_key_env or "OPENROUTER_API_KEY",args.timeout)
        report = asyncio.run(diagnose(scenario,config,live=args.live))
        # Diagnostics contain only static identifiers, booleans, counts and lengths.
        print(json.dumps(report,ensure_ascii=False,allow_nan=False))
        return 0 if report.get("dry_run") or report["completed"] else 1
    except Exception:
        print("FAIL: diagnostic configuration, credentials, DEV identity or infrastructure.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
