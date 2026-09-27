"""Run the eval set against a reviewer and (optionally) enforce the CI regression gate.

    uv run ccr-eval                          # production reviewer, print scorecard
    uv run ccr-eval --gate                   # fail if below evals/gate.json thresholds
    uv run ccr-eval --update-gate            # promote current numbers to the gate

The gate is a floor, not a target. It exists so nobody can merge a change that makes the
reviewer worse without deciding to.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from evals.report import print_terminal, write_reports
from evals.schema import CASES_DIR, CONTRACTS_DIR, load_cases, validate_against_contracts
from evals.scoring import Scorecard, build_scorecard, score_case
from reviewer.baselines import get_reviewer

ROOT = Path(__file__).resolve().parent.parent
GATE_PATH = ROOT / "evals" / "gate.json"
RESULTS_DIR = ROOT / "evals" / "results"
SVG_PATH = ROOT / "docs" / "img" / "scorecard.svg"
MD_PATH = ROOT / "docs" / "scorecard.md"

# Metrics where higher is better and where lower is better, for gate comparison.
HIGHER_BETTER = ("presence_accuracy", "span_recall", "citation_precision")
LOWER_BETTER = ("false_refusal_rate", "hallucinated_presence_rate")
TOLERANCE = 0.01  # one percentage point of noise allowed


def run(reviewer_name: str) -> Scorecard:
    cases = load_cases(CASES_DIR)
    problems = validate_against_contracts(cases, CONTRACTS_DIR)
    if problems:
        for p in problems[:20]:
            print(f"eval set problem: {p}", file=sys.stderr)
        raise SystemExit(f"{len(problems)} eval-set problems; fix cases before running")

    reviewer = get_reviewer(reviewer_name)
    text_cache: dict[str, str] = {}
    results = []
    for case in cases:
        if case.contract not in text_cache:
            text_cache[case.contract] = case.contract_text(CONTRACTS_DIR)
        finding = reviewer.review(text_cache[case.contract], case.clause_type, case.question)
        results.append(score_case(case, finding))
    return build_scorecard(reviewer.name, results)


def check_gate(card: Scorecard, gate_path: Path) -> list[str]:
    if not gate_path.exists():
        return [f"no gate file at {gate_path}; run with --update-gate to create one"]
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    current = card.overall.as_dict()
    failures = []
    for metric in HIGHER_BETTER:
        if metric in gate and current[metric] < gate[metric] - TOLERANCE:
            failures.append(f"{metric}: {current[metric]:.3f} < gate {gate[metric]:.3f}")
    for metric in LOWER_BETTER:
        if metric in gate and current[metric] > gate[metric] + TOLERANCE:
            failures.append(f"{metric}: {current[metric]:.3f} > gate {gate[metric]:.3f}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--reviewer", default="retrieval-hybrid")
    parser.add_argument("--gate", action="store_true", help="fail if below evals/gate.json")
    parser.add_argument(
        "--update-gate", action="store_true", help="write current overall metrics to gate"
    )
    parser.add_argument("--no-report", action="store_true", help="skip writing SVG/Markdown/JSON")
    args = parser.parse_args(argv)

    card = run(args.reviewer)
    print_terminal(card)

    if not args.no_report:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            **card.as_dict(),
        }
        (RESULTS_DIR / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        write_reports(card, SVG_PATH, MD_PATH)
        print(f"\nwrote {RESULTS_DIR / 'latest.json'}, {SVG_PATH}, {MD_PATH}")

    if args.update_gate:
        GATE_PATH.write_text(json.dumps(card.overall.as_dict(), indent=2), encoding="utf-8")
        print(f"gate updated: {GATE_PATH}")

    if args.gate:
        failures = check_gate(card, GATE_PATH)
        if failures:
            print("\nREGRESSION GATE FAILED:")
            for f in failures:
                print(f"  - {f}")
            return 1
        print("\nregression gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
