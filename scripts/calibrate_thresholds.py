"""Sweep presence thresholds for the retrieval reviewer and print the tradeoff table.

    uv run python -m scripts.calibrate_thresholds

For every eval case, record the top BM25 score and the top dense cosine similarity. Then
for a grid of thresholds report presence accuracy, false refusal rate, and hallucinated
presence rate. The output feeds ADR-0002; the chosen values go in RetrievalConfig.

Honesty note: calibrating on the same 120 cases we report on is optimistic. The table
also prints a per-contract leave-one-out score so the optimism is visible.
"""

from __future__ import annotations

from collections import defaultdict

from evals.schema import CASES_DIR, CONTRACTS_DIR, load_cases
from reviewer.chunking import chunk_text
from reviewer.pipeline import clause_query
from reviewer.retrieval import Index


def collect() -> list[tuple[str, bool, float, float]]:
    cases = load_cases(CASES_DIR)
    by_contract: dict[str, list] = defaultdict(list)
    for c in cases:
        by_contract[c.contract].append(c)
    rows = []
    for contract, group in by_contract.items():
        text = group[0].contract_text(CONTRACTS_DIR)
        index = Index(chunk_text(text), mode="hybrid")
        for c in group:
            q = clause_query(c.clause_type)
            bm25_top = index._bm25_ranked(q)[0][1]
            dense_top = index._dense_ranked(q)[0][1]
            rows.append((contract, c.expected.present, float(bm25_top), float(dense_top)))
    return rows


def evaluate(rows, bm25_t: float, dense_t: float, rule: str) -> tuple[float, float, float]:
    correct = fr = hp = 0
    n_present = sum(1 for r in rows if r[1])
    n_absent = len(rows) - n_present
    for _, expected, b, d in rows:
        if rule == "bm25":
            predicted = b >= bm25_t
        elif rule == "dense":
            predicted = d >= dense_t
        elif rule == "either":
            predicted = b >= bm25_t or d >= dense_t
        else:  # both
            predicted = b >= bm25_t and d >= dense_t
        correct += predicted == expected
        fr += expected and not predicted
        hp += (not expected) and predicted
    return correct / len(rows), fr / max(1, n_present), hp / max(1, n_absent)


def main() -> int:
    rows = collect()
    print(f"{len(rows)} cases; present={sum(r[1] for r in rows)} absent={sum(not r[1] for r in rows)}")
    print("\nrule    bm25_t dense_t | presence_acc false_refusal hallucinated")
    best = None
    for rule in ("bm25", "dense", "either", "both"):
        for bm25_t in (3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0):
            for dense_t in (0.60, 0.65, 0.70, 0.72, 0.75, 0.78, 0.80):
                if rule == "bm25" and dense_t != 0.60:
                    continue
                if rule == "dense" and bm25_t != 3.0:
                    continue
                acc, fr, hp = evaluate(rows, bm25_t, dense_t, rule)
                # objective: accuracy, but never let false refusal above 25% (missing clauses
                # is the customer's worst outcome)
                score = acc if fr <= 0.25 else acc - 1
                if best is None or score > best[0]:
                    best = (score, rule, bm25_t, dense_t, acc, fr, hp)
                if rule in ("bm25", "dense") or dense_t in (0.70, 0.75) and bm25_t in (5.0, 7.0):
                    print(f"{rule:7} {bm25_t:6.1f} {dense_t:7.2f} | {acc:11.0%} {fr:13.0%} {hp:12.0%}")
    _, rule, bm25_t, dense_t, acc, fr, hp = best
    print(
        f"\nbest (false refusal <= 25%): rule={rule} bm25>={bm25_t} dense>={dense_t}"
        f"  acc={acc:.0%} false_refusal={fr:.0%} hallucinated={hp:.0%}"
    )

    # leave-one-contract-out with the best rule, to show how much the number moves
    contracts = sorted({r[0] for r in rows})
    loo = []
    for held in contracts:
        test = [r for r in rows if r[0] == held]
        acc_h, _, _ = evaluate(test, bm25_t, dense_t, rule)
        loo.append(acc_h)
    print(
        f"leave-one-contract-out presence accuracy: min={min(loo):.0%} max={max(loo):.0%} "
        f"mean={sum(loo) / len(loo):.0%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
