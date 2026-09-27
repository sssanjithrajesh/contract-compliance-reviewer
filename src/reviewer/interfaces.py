"""Core contracts every reviewer implementation must satisfy.

Design note: a `Finding` is deliberately small. It says whether the clause is present,
where exactly in the document the evidence is (character spans, so a UI can highlight
and a lawyer can verify), and how confident the system is. Anything a reviewer cannot
cite, it must not claim. That rule is enforced by the eval harness, not by convention.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator


class Span(BaseModel):
    """A half-open character range [start, end) into the contract text."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = ""

    @model_validator(mode="after")
    def _check_order(self) -> Span:
        if self.end < self.start:
            raise ValueError(f"span end {self.end} < start {self.start}")
        return self

    def overlap(self, other: Span) -> int:
        """Number of overlapping characters with another span."""
        return max(0, min(self.end, other.end) - max(self.start, other.start))

    def __len__(self) -> int:
        return self.end - self.start


class Finding(BaseModel):
    """What a reviewer says about one clause type in one contract."""

    present: bool
    spans: list[Span] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _absent_means_no_spans(self) -> Finding:
        # A refusal ("not present") with citations attached is a contradiction.
        if not self.present and self.spans:
            raise ValueError("a finding marked absent must not carry spans")
        return self

    @classmethod
    def absent(cls, rationale: str = "", confidence: float = 0.0) -> Finding:
        return cls(present=False, spans=[], rationale=rationale, confidence=confidence)


@runtime_checkable
class Reviewer(Protocol):
    """Anything that can answer 'is this clause in this contract, and where?'."""

    name: str

    def review(self, contract_text: str, clause_type: str, question: str) -> Finding: ...
