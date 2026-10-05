"""Offline structure/consistency check for the synthetic response-quality corpus."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.quality_evaluation.contract import QualityContractError, load_corpus


def main():
    try:
        corpus = load_corpus()
    except QualityContractError:
        print("FAIL: invalid response-quality corpus or expected-result contract")
        return 1
    for case in corpus["cases"]:
        print("PASS " + case["id"])
    print(f"Summary: {len(corpus['cases'])}/{len(corpus['cases'])} passed (quality contract only; no model calls).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
