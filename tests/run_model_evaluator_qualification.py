"""Explicitly gated model qualification; default behavior is an offline dry run."""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.evaluation.contract import ContractError
from services.evaluation.model_adapter import AdapterError, ModelConfig, OpenAICompatibleAdapter, sanitize
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = ModelConfig(args.model, args.base_url, args.timeout, args.api_key_env).validate()
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
        print(f"DRY RUN: model={sanitize(config.model)}; planned_cases={len(cases)}; timeout={config.timeout:g}s")
        print("Prompts built; zero network calls; no artifacts written. API credentials are required only for --live.")
        return 0
    # Do not print the URL, credentials, headers, model response, or environment.
    secret = os.environ.get(config.api_key_env)
    if not secret or not secret.strip():
        print("FAIL: required API credential is missing.")
        return 2
    try:
        report = qualify(cases, builder, OpenAICompatibleAdapter(config), config,
                         live=True, project_root=PROJECT_ROOT, secret=secret)
        artifact = write_report(report, secret=secret, project_root=PROJECT_ROOT)
    except (AdapterError, ContractError, ValueError, OSError, UnicodeError):
        print("FAIL: qualification or artifact infrastructure error.")
        return 1
    for record in report["cases"]:
        status = "INFRA_FAIL" if record["error"] else "MATCH" if record["comparison"]["matches"]["full_result"] else "MISMATCH"
        print(f"{status} {record['case_id']}")
    print(f"Summary: {len(cases)} cases; infrastructure_failures={report['metrics']['infrastructure_failures']}; semantic_label_mismatches={report['metrics']['semantic_label_mismatch_cases']}")
    print("Report:", artifact.relative_to(PROJECT_ROOT))
    return 1 if report["metrics"]["infrastructure_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
