"""How a Finding is scored against an EvalCase.

Four numbers, chosen because each maps to a question a lawyer would ask:

- presence_accuracy   "Did it correctly say whether the clause exists?"
- span_recall         "When the clause exists, did it find the actual text?"
- citation_precision  "When it cited something, was the citation real evidence?"
- false_refusal_rate  "How often did it say 'not found' when the clause was there?"

Span matching is character-overlap based. A predicted span "hits" an expected span if it
covers at least `COVERAGE_THRESHOLD` of the expected characters. Pure token-F1 would
reward citing an entire page; coverage of the expected span does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evals.schema import EvalCase
from reviewer.interfaces import Finding, Span

COVERAGE_THRESHOLD = 0.5


@dataclass
class CaseResult:
    case_id: str
    clause_type: str
    expected_present: bool
    predicted_present: bool
    expected_spans: int
    hit_spans: int
    predicted_spans: int
    grounded_predictions: int

    @property
    def presence_correct(self) -> bool:
        return self.expected_present == self.predicted_present

    @property
    def false_refusal(self) -> bool:
        return self.expected_present and not self.predicted_present

    @property
    def hallucinated_presence(self) -> bool:
        return not self.expected_present and self.predicted_present


def _covered(expected: Span, predicted: list[Span]) -> bool:
    if len(expected) == 0:
        return False
    covered = sum(p.overlap(expected) for p in predicted)
    return covered / len(expected) >= COVERAGE_THRESHOLD


def _grounded(predicted: Span, expected: list[Span]) -> bool:
    return any(predicted.overlap(e) > 0 for e in expected)


def score_case(case: EvalCase, finding: Finding) -> CaseResult:
    expected_spans = [s.as_span() for s in case.expected.spans]
    hit = sum(1 for e in expected_spans if _covered(e, finding.spans))
    grounded = sum(1 for p in finding.spans if _grounded(p, expected_spans))
    return CaseResult(
        case_id=case.id,
        clause_type=case.clause_type,
        expected_present=case.expected.present,
        predicted_present=finding.present,
        expected_spans=len(expected_spans),
        hit_spans=hit,
        predicted_spans=len(finding.spans),
        grounded_predictions=grounded,
    )


@dataclass
class Metrics:
    n: int = 0
    presence_accuracy: float = 0.0
    span_recall: float = 0.0
    citation_precision: float = 0.0
    false_refusal_rate: float = 0.0
    hallucinated_presence_rate: float = 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "presence_accuracy": round(self.presence_accuracy, 4),
            "span_recall": round(self.span_recall, 4),
            "citation_precision": round(self.citation_precision, 4),
            "false_refusal_rate": round(self.false_refusal_rate, 4),
            "hallucinated_presence_rate": round(self.hallucinated_presence_rate, 4),
        }


def aggregate(results: list[CaseResult]) -> Metrics:
    if not results:
        return Metrics()
    n = len(results)
    present = [r for r in results if r.expected_present]
    absent = [r for r in results if not r.expected_present]
    exp_spans = sum(r.expected_spans for r in results)
    pred_spans = sum(r.predicted_spans for r in results)
    return Metrics(
        n=n,
        presence_accuracy=sum(r.presence_correct for r in results) / n,
        span_recall=(sum(r.hit_spans for r in results) / exp_spans) if exp_spans else 0.0,
        citation_precision=(sum(r.grounded_predictions for r in results) / pred_spans if pred_spans else 0.0),
        false_refusal_rate=(sum(r.false_refusal for r in present) / len(present) if present else 0.0),
        hallucinated_presence_rate=(sum(r.hallucinated_presence for r in absent) / len(absent) if absent else 0.0),
    )


@dataclass
class Scorecard:
    reviewer: str
    overall: Metrics
    by_clause_type: dict[str, Metrics] = field(default_factory=dict)
    results: list[CaseResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "reviewer": self.reviewer,
            "overall": self.overall.as_dict(),
            "by_clause_type": {k: v.as_dict() for k, v in sorted(self.by_clause_type.items())},
        }


def build_scorecard(reviewer_name: str, results: list[CaseResult]) -> Scorecard:
    by_type: dict[str, list[CaseResult]] = {}
    for r in results:
        by_type.setdefault(r.clause_type, []).append(r)
    return Scorecard(
        reviewer=reviewer_name,
        overall=aggregate(results),
        by_clause_type={k: aggregate(v) for k, v in by_type.items()},
        results=results,
    )
