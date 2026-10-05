"""Explicitly gated synthetic DEV conversation benchmark; default offline plan."""
import argparse
import asyncio
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from services.conversation_benchmark import BenchmarkConfig, load_scenarios, select_scenarios, run_benchmark, write_report
from services.evaluation.runtime import ShadowConfig
from services.quality_evaluation.runtime import QualityShadowConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live",action="store_true")
    mode.add_argument("--dry-run",action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--scenario-id",action="append")
    parser.add_argument("--max-scenarios",type=int)
    parser.add_argument("--generator-max-tokens",type=int,default=350)
    parser.add_argument("--timeout",type=float,default=60)
    parser.add_argument("--methodology-model",default="z-ai/glm-5.2")
    parser.add_argument("--quality-model",default="z-ai/glm-5.2")
    parser.add_argument("--evaluator-base-url",default="https://openrouter.ai/api/v1")
    args = parser.parse_args(argv)
    try:
        if args.live and not all((args.model,args.base_url,args.api_key_env)):
            raise ValueError("Explicit live configuration required")
        config = BenchmarkConfig(args.model or "offline-plan", args.base_url or "https://offline.invalid/v1",
                                 args.api_key_env or "OPENROUTER_API_KEY", args.timeout,args.generator_max_tokens)
        scenarios = select_scenarios(load_scenarios(),args.scenario_id,args.max_scenarios)
        report = asyncio.run(run_benchmark(scenarios,config,live=args.live,
            methodology_config=ShadowConfig(enabled=True,model=args.methodology_model,base_url=args.evaluator_base_url),
            quality_config=QualityShadowConfig(enabled=True,model=args.quality_model,base_url=args.evaluator_base_url)))
        if not args.live:
            print(f"DRY RUN: {report['scenario_count']} scenarios / {report['turn_count']} turns; generator max_tokens={config.generator_max_tokens}.")
            print("Zero network calls; zero credential lookups; zero DB/Telegram access; no artifacts written.")
            return 0
        artifact = write_report(report)
        print("Report:",artifact.relative_to(ROOT))
        print("Generated turns:", report["metrics"]["generated_turns"])
        return 1 if any(report["metrics"]["infrastructure"][k] for k in ("generator_failures","methodology_evaluator_failures","quality_evaluator_failures")) else 0
    except Exception:
        # Never print provider exceptions, configuration values or conversation data.
        print("FAIL: benchmark configuration, credentials, DEV identity, source or infrastructure check.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
