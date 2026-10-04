"""Offline corpus contract runner; never evaluates response semantics."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.evaluation import ContractError, load_corpus, validate_case


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="?", type=Path,
                        default=PROJECT_ROOT / "tests/coaching_evaluator_cases.json",
                        help="Corpus under repository tests/; relative paths start at repository root")
    args = parser.parse_args(argv)
    try:
        corpus = load_corpus(args.corpus, PROJECT_ROOT)
    except ContractError as exc:
        print(f"FAIL corpus: {exc}")
        print("Summary: corpus could not be validated.")
        return 1
    failed = 0
    for case in corpus["cases"]:
        try:
            validate_case(case, PROJECT_ROOT)
        except ContractError as exc:
            failed += 1
            print(f"FAIL {case['id']}: {exc}")
        else:
            print(f"PASS {case['id']}")
    total = len(corpus["cases"])
    print(f"Summary: {total - failed}/{total} passed; {failed} failed (contract only).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
