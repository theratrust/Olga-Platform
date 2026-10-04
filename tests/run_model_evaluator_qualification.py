"""Explicitly gated model qualification; default behavior is an offline dry run."""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.evaluation.contract import ContractError
from services.evaluation.model_adapter import AdapterError, ModelConfig, OpenAICompatibleAdapter, sanitize, parse_model_json
from services.evaluation.prompt import EvaluatorPromptBuilder
from services.evaluation.qualification import load_labeled_cases, qualify, select_cases, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL, including /v1 where needed")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--no-structural-retry", action="store_true")
    parser.add_argument("--max-tokens", "--max-output-tokens", type=int, default=2500)
    parser.add_argument("--reasoning-format", choices=("reasoning", "reasoning_effort"), default="reasoning")
    reasoning = parser.add_mutually_exclusive_group()
    reasoning.add_argument("--reasoning-effort", choices=("low", "medium", "high", "minimal", "none"))
    reasoning.add_argument("--reasoning-budget", type=int)
    reasoning.add_argument("--reasoning-json", help="Provider-specific reasoning object; no provider support is assumed")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        reasoning_config = None
        reasoning_effort = None
        if args.reasoning_effort is not None:
            if args.reasoning_format == "reasoning_effort":
                reasoning_effort = args.reasoning_effort
            else:
                reasoning_config = {"effort": args.reasoning_effort}
        if args.reasoning_budget is not None or args.reasoning_json is not None:
            if args.reasoning_format != "reasoning":
                raise ValueError("Budget/JSON configuration requires reasoning object format")
            reasoning_config = ({"max_tokens": args.reasoning_budget} if args.reasoning_budget is not None
                                else parse_model_json(args.reasoning_json))
        config = ModelConfig(args.model, args.base_url, args.timeout, args.api_key_env,
                             args.max_tokens, reasoning_config, reasoning_effort).validate()
        labeled = load_labeled_cases(PROJECT_ROOT)
        try:
            cases = select_cases(labeled, args.case_id, args.max_cases)
        except ValueError:
            print("FAIL: unknown/duplicate case ID or invalid --max-cases selection.")
            return 2
        builder = EvaluatorPromptBuilder(PROJECT_ROOT)
        for case in cases:
            builder.build(case["input"])
    except (AdapterError, ContractError, ValueError, OSError, UnicodeError):
        print("FAIL: invalid configuration, corpus, selection, or prompt sources.")
        return 2
    if not args.live:
        print(f"DRY RUN: model={sanitize(config.model)}; planned_cases={len(cases)}; timeout={config.timeout:g}s; max_tokens={config.max_tokens}")
        print("Reasoning configuration:", sanitize(config.reasoning or config.reasoning_effort or "omitted"))
        print(f"Structural retry: max_attempts={1 if args.no_structural_retry else 2}; no transport/provider retries.")
        print("Prompts built; zero network calls; no artifacts written. API credentials are required only for --live.")
        return 0
    # Do not print the URL, credentials, headers, model response, or environment.
    secret = os.environ.get(config.api_key_env)
    if not secret or not secret.strip():
        print("FAIL: required API credential is missing.")
        return 2
    try:
        report = qualify(cases, builder, OpenAICompatibleAdapter(config), config,
                         live=True, project_root=PROJECT_ROOT, secret=secret, retry_enabled=not args.no_structural_retry)
        artifact = write_report(report, secret=secret, project_root=PROJECT_ROOT)
    except (AdapterError, ContractError, ValueError, OSError, UnicodeError):
        print("FAIL: qualification or artifact infrastructure error.")
        return 1
    for record in report["cases"]:
        prefix = "RECOVERED_" if record.get("recovered") else ""
        print(f"{prefix}{record['outcome']} {record['case_id']}")
    metrics = report["metrics"]
    print(f"Summary: {len(cases)} cases; infrastructure_failures={metrics['infrastructure_failures']}; "
          f"routing_semantic_mismatches={metrics['routing_semantic_mismatch_cases']}; "
          f"routing_match_taxonomy_variance={metrics['routing_match_taxonomy_variance_cases']}; "
          f"semantic_pass_detail_variance={metrics['semantic_pass_detail_variance']}; "
          f"exact_matches={metrics['exact_matches']}")
    print(f"Reliability: first_pass_infrastructure_failures={metrics['first_pass_infrastructure_failures']}; "
          f"retry_attempted_cases={metrics['retry_attempted_cases']}; "
          f"retry_recovered_cases={metrics['retry_recovered_cases']}; "
          f"final_infrastructure_failures={metrics['final_infrastructure_failures']}")
    print("Report:", artifact.relative_to(PROJECT_ROOT))
    return 1 if report["metrics"]["infrastructure_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
