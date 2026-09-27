from evals.schema import EvalCase
from evals.scoring import aggregate, build_scorecard, score_case
from reviewer.interfaces import Finding, Span

TEXT = "This Agreement shall be governed by the laws of the State of Delaware. Other text here."
GOV = TEXT.index("governed by")
GOV_END = TEXT.index("Delaware") + len("Delaware")


def present_case() -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "c1__governing_law",
            "contract": "c1",
            "clause_type": "governing_law",
            "question": "Which law governs?",
            "expected": {
                "present": True,
                "spans": [{"start": GOV, "end": GOV_END, "text": TEXT[GOV:GOV_END]}],
            },
            "source": {"dataset": "manual", "id": "t1"},
        }
    )


def absent_case() -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "c1__insurance",
            "contract": "c1",
            "clause_type": "insurance",
            "question": "Insurance?",
            "expected": {"present": False, "spans": []},
            "source": {"dataset": "manual", "id": "t2"},
        }
    )


def test_exact_hit_scores_full_recall_and_precision():
    r = score_case(present_case(), Finding(present=True, spans=[Span(start=GOV, end=GOV_END)]))
    assert r.presence_correct and r.hit_spans == 1 and r.grounded_predictions == 1


def test_partial_overlap_below_threshold_is_a_miss_but_still_grounded():
    tiny = Span(start=GOV, end=GOV + 3)  # covers well under 50% of the expected span
    r = score_case(present_case(), Finding(present=True, spans=[tiny]))
    assert r.hit_spans == 0
    assert r.grounded_predictions == 1  # it did touch real evidence


def test_ungrounded_citation_counts_against_precision():
    r = score_case(present_case(), Finding(present=True, spans=[Span(start=0, end=4)]))
    assert r.grounded_predictions == 0 and r.predicted_spans == 1


def test_false_refusal_and_hallucination_flags():
    fr = score_case(present_case(), Finding.absent())
    assert fr.false_refusal and not fr.presence_correct
    hal = score_case(absent_case(), Finding(present=True, spans=[Span(start=0, end=4)]))
    assert hal.hallucinated_presence and not hal.presence_correct


def test_aggregate_and_scorecard():
    results = [
        score_case(present_case(), Finding(present=True, spans=[Span(start=GOV, end=GOV_END)])),
        score_case(absent_case(), Finding.absent()),
    ]
    m = aggregate(results)
    assert m.n == 2 and m.presence_accuracy == 1.0 and m.span_recall == 1.0
    assert m.false_refusal_rate == 0.0 and m.hallucinated_presence_rate == 0.0
    card = build_scorecard("test", results)
    assert set(card.by_clause_type) == {"governing_law", "insurance"}
    assert card.as_dict()["overall"]["n"] == 2


def test_aggregate_empty_is_zero():
    assert aggregate([]).n == 0
