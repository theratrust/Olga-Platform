"""Explicit DEV paired soak. Default dry-run; no credential lookup or artifacts."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services.conversation_benchmark import BenchmarkConfig
from services.overnight_ab_soak import run_soak


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group();mode.add_argument("--live",action="store_true");mode.add_argument("--dry-run",action="store_true")
    parser.add_argument("--candidate-id");parser.add_argument("--model");parser.add_argument("--base-url");parser.add_argument("--api-key-env")
    parser.add_argument("--timeout",type=float,default=60);parser.add_argument("--paired-trials",type=int,default=10)
    parser.add_argument("--baseline-source",type=Path);parser.add_argument("--run-id")
    args=parser.parse_args(argv)
    try:
        if args.live and not all([args.candidate_id,args.model,args.base_url,args.api_key_env]):raise ValueError("Explicit live configuration required")
        config=BenchmarkConfig(args.model or "offline-plan",args.base_url or "https://offline.invalid/v1",args.api_key_env or "OPENROUTER_API_KEY",args.timeout)
        result=asyncio.run(run_soak(config,args.paired_trials,live=args.live,baseline_source=args.baseline_source,run_id=args.run_id,candidate_id=args.candidate_id))
        print(json.dumps(result,allow_nan=False),flush=True)
        return 0 if result.get("dry_run") or result["completion_status"]=="completed" else 1
    except Exception:
        print("FAIL: soak configuration, frozen source, DEV identity or infrastructure check.",flush=True)
        return 2


if __name__=="__main__":raise SystemExit(main())
