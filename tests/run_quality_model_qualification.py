"""Model selection for derived response quality; default zero-network dry run."""
import argparse
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.quality_evaluation.contract import QualityContractError
from services.quality_evaluation.prompt import QualityPromptBuilder
from services.quality_evaluation.model_adapter import AdapterError, ModelConfig, OpenAICompatibleAdapter
from services.quality_evaluation.qualification import load_labeled_cases, select_cases, qualify, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--max-tokens", "--max-output-tokens", type=int, default=2500)
    parser.add_argument("--reasoning-effort", choices=("none", "minimal", "low", "medium", "high"))
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--max-cases", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.live and (not args.model or not args.base_url):
            raise ValueError("Explicit model and base URL required")
        config = ModelConfig(args.model or "offline-plan", args.base_url or "https://offline.invalid/v1",
                             args.timeout, args.api_key_env, args.max_tokens, reasoning_effort=args.reasoning_effort).validate()
        cases = select_cases(load_labeled_cases(), args.case_id, args.max_cases)
        builder = QualityPromptBuilder()
        adapter = OpenAICompatibleAdapter(config) if args.live else None
        report = qualify(cases, builder, adapter, config, live=args.live)
        if not args.live:
            print(f"DRY RUN: {len(cases)} cases; zero network calls; no artifacts written; max_attempts=2.")
            return 0
        path = write_report(report, secret=os.environ.get(config.api_key_env))
        for record in report["cases"]:
            print(record["outcome"], record["case_id"])
        print("Report:", path.relative_to(ROOT))
        return 1 if report["metrics"]["final_infrastructure_failures"] else 0
    except (AdapterError, QualityContractError, ValueError, OSError):
        print("FAIL: invalid configuration, missing credentials, corpus, or artifact failure.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
