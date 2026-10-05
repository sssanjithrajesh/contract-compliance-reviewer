import pytest
from pydantic import ValidationError

from reviewer.interfaces import Finding, Span


def test_span_overlap():
    a = Span(start=0, end=10, text="0123456789")
    b = Span(start=5, end=15, text="")
    assert a.overlap(b) == 5
    assert b.overlap(a) == 5
    assert a.overlap(Span(start=10, end=20)) == 0


def test_span_rejects_reversed_range():
    with pytest.raises(ValidationError):
        Span(start=5, end=2)


def test_absent_finding_cannot_carry_spans():
    with pytest.raises(ValidationError):
        Finding(present=False, spans=[Span(start=0, end=1, text="x")])


def test_absent_helper():
    f = Finding.absent(rationale="nope")
    assert f.present is False and f.spans == [] and f.rationale == "nope"
