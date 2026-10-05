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
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from evals.report import print_terminal, write_reports
from evals.schema import CASES_DIR, CONTRACTS_DIR, load_cases, validate_against_contracts
from evals.scoring import Scorecard, build_scorecard, score_case
from reviewer.baselines import get_reviewer

ROOT = Path(__file__).resolve().parent.parent
GATE_PATH = ROOT / "evals" / "gate.json"


def _load_dotenv() -> None:
    """Pull KEY=value lines from .env into os.environ. Never prints values."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
RESULTS_DIR = ROOT / "evals" / "results"
SVG_PATH = ROOT / "docs" / "img" / "scorecard.svg"
MD_PATH = ROOT / "docs" / "scorecard.md"

# Metrics where higher is better and where lower is better, for gate comparison.
HIGHER_BETTER = ("presence_accuracy", "span_recall", "citation_precision")
LOWER_BETTER = ("false_refusal_rate", "hallucinated_presence_rate")
TOLERANCE = 0.01  # one percentage point of noise allowed
GATE_CUSTOMER = "harlow-pryce"  # the CUAD-backed set; the CI gate tracks this customer's clauses


def run(reviewer_name: str, customer_id: str | None = None) -> Scorecard:
    cases = load_cases(CASES_DIR)
    if customer_id:
        from reviewer.config import load_customer

        wanted = set(load_customer(customer_id).clauses)
        cases = [c for c in cases if c.clause_type in wanted]
        if not cases:
            raise SystemExit(f"no eval cases cover customer {customer_id!r} clause types")
    problems = validate_against_contracts(cases, CONTRACTS_DIR)
    if problems:
        for p in problems[:20]:
            print(f"eval set problem: {p}", file=sys.stderr)
        raise SystemExit(f"{len(problems)} eval-set problems; fix cases before running")

    reviewer = get_reviewer(reviewer_name)
    text_cache: dict[str, str] = {}
    results = []
    timings: list[float] = []
    t0 = time.perf_counter()
    for case in cases:
        if case.contract not in text_cache:
            text_cache[case.contract] = case.contract_text(CONTRACTS_DIR)
        started = time.perf_counter()
        finding = reviewer.review(text_cache[case.contract], case.clause_type, case.question)
        timings.append(time.perf_counter() - started)
        results.append(score_case(case, finding))
    card = build_scorecard(reviewer.name, results)
    card.latency_s = {
        "n": len(timings),
        "total": round(time.perf_counter() - t0, 3),
        "p50": round(statistics.median(timings), 4) if timings else 0.0,
        "p95": round(sorted(timings)[max(0, int(len(timings) * 0.95) - 1)], 4) if timings else 0.0,
    }
    return card


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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reviewer", default="retrieval-hybrid")
    parser.add_argument("--gate", action="store_true", help="fail if below evals/gate.json")
    parser.add_argument("--update-gate", action="store_true", help="write current overall metrics to gate")
    parser.add_argument("--no-report", action="store_true", help="skip writing SVG/Markdown/JSON")
    parser.add_argument(
        "--customer",
        default=GATE_CUSTOMER,
        help=f"score only the clause types this customer checks (default {GATE_CUSTOMER}; the gate tracks it)",
    )
    args = parser.parse_args(argv)
    _load_dotenv()

    if args.reviewer == "llm" and not os.environ.get("ANTHROPIC_API_KEY"):
        skip = ROOT / "docs" / "llm-eval.md"
        skip.write_text(
            "\n".join(
                [
                    "### LLM extraction — not scored on this machine",
                    "",
                    "`ANTHROPIC_API_KEY` is unset. `LLMReviewer` is wired and unit-tested",
                    "against a fake client (verbatim quotes only; fabricated quotes are dropped).",
                    "The 120-case run is skipped so CI and local machines without a key stay green.",
                    "",
                    "To score it:",
                    "",
                    "```",
                    "set ANTHROPIC_API_KEY=...",
                    "uv run ccr-eval --reviewer llm",
                    "```",
                    "",
                    "Keep the row only if hallucinated presence and citation precision beat",
                    "`retrieval-hybrid` (currently 3% and 55%). Otherwise the local engine stays",
                    "the production default — that is the eval-driven call OpenAI's JD asks for.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"llm eval skipped (no ANTHROPIC_API_KEY); wrote {skip}")
        return 0

    card = run(args.reviewer, args.customer)
    print_terminal(card)
    suffix = "" if args.customer == GATE_CUSTOMER else f"-{args.customer}"
    if args.reviewer == "llm":
        suffix = f"{suffix}-llm" if suffix else "-llm"
    svg_path = SVG_PATH.with_name(f"scorecard{suffix}.svg")
    md_path = MD_PATH.with_name(f"scorecard{suffix}.md")
    latest_path = RESULTS_DIR / f"latest{suffix}.json"

    if not args.no_report:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "customer": args.customer,
            **card.as_dict(),
        }
        latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        write_reports(card, svg_path, md_path)
        if card.latency_s:
            bench = ROOT / "docs" / ("benchmark-llm.md" if args.reviewer == "llm" else "benchmark.md")
            lat = card.latency_s
            m = card.overall
            bench.write_text(
                "\n".join(
                    [
                        "### Latency and quality (this machine)",
                        "",
                        "| Measure | Value | What a partner should take from it |",
                        "|---|---:|---|",
                        f"| Cases | {lat['n']} | Same 120 CUAD-backed questions every run |",
                        f"| p50 per question | {lat['p50']*1000:.0f} ms | Typical look-up |",
                        f"| p95 per question | {lat['p95']*1000:.0f} ms | Slow tail; first contract pays for embedding |",
                        f"| Wall time for the set | {lat['total']:.1f} s | Includes model load |",
                        f"| Hallucinated presence | {m.hallucinated_presence_rate:.0%} | How often we invent a missing clause |",
                        f"| Citation precision | {m.citation_precision:.0%} | Cited span overlaps expert evidence |",
                        "",
                        "API token cost is $0 on `retrieval-hybrid` (local embeddings). "
                        "`llm` is unmeasured until `ANTHROPIC_API_KEY` is set; then this table "
                        "gains a `$ / review` row from the provider usage object.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        print(f"\nwrote {latest_path}, {svg_path}, {md_path}")

    if args.update_gate and args.customer != GATE_CUSTOMER:
        raise SystemExit(f"the regression gate tracks the {GATE_CUSTOMER} set; run --update-gate without --customer")
    if args.update_gate:
        GATE_PATH.write_text(json.dumps(card.overall.as_dict(), indent=2), encoding="utf-8")
        print(f"gate updated: {GATE_PATH}")

    if args.gate and args.customer != GATE_CUSTOMER:
        print(f"\n(gate only applies to the {GATE_CUSTOMER} set; skipped)")
    elif args.gate:
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
