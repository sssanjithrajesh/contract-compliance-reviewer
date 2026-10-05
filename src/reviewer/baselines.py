"""Deliberately simple reviewers that set the floor the real system must beat.

`KeywordBaseline` is what a weekend script would do: find sentences containing clause
keywords and cite them. It is here so the first eval number is honest and so every
later improvement can be measured against something concrete.
"""

from __future__ import annotations

import re

from reviewer.clauses import CLAUSE_TYPES
from reviewer.interfaces import Finding, Span

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.;:])\s+|\n{2,}")


def _sentences(text: str) -> list[Span]:
    """Split text into rough sentence spans with character offsets preserved."""
    spans: list[Span] = []
    pos = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        end = match.start()
        if end > pos:
            spans.append(Span(start=pos, end=end, text=text[pos:end]))
        pos = match.end()
    if pos < len(text):
        spans.append(Span(start=pos, end=len(text), text=text[pos:]))
    return spans


class KeywordBaseline:
    """Cites any sentence that contains a clause keyword. No understanding, no ranking."""

    name = "keyword"

    def __init__(self, max_spans: int = 3) -> None:
        self.max_spans = max_spans

    def review(self, contract_text: str, clause_type: str, question: str) -> Finding:
        ct = CLAUSE_TYPES.get(clause_type)
        if ct is None:
            return Finding.absent(rationale=f"unknown clause type {clause_type!r}")

        lowered = contract_text.lower()
        keywords = [k.lower() for k in ct.keywords]
        hits: list[Span] = []
        for sentence in _sentences(contract_text):
            window = lowered[sentence.start : sentence.end]
            if any(k in window for k in keywords):
                hits.append(sentence)
                if len(hits) >= self.max_spans:
                    break

        if not hits:
            return Finding.absent(rationale="no keyword matches", confidence=0.3)
        return Finding(
            present=True,
            spans=hits,
            rationale=f"matched keywords for {ct.cuad_name}",
            confidence=0.5,
        )


class AlwaysAbsent:
    """Refuses everything. Useful for checking that the harness penalises false refusals."""

    name = "always_absent"

    def review(self, contract_text: str, clause_type: str, question: str) -> Finding:
        return Finding.absent(rationale="baseline: always absent", confidence=1.0)


def _retrieval(mode: str):
    from reviewer.pipeline import RetrievalConfig, RetrievalReviewer

    return RetrievalReviewer(RetrievalConfig(mode=mode))


def _llm():
    from reviewer.pipeline import LLMReviewer

    return LLMReviewer()


REGISTRY: dict[str, object] = {
    KeywordBaseline.name: KeywordBaseline,
    AlwaysAbsent.name: AlwaysAbsent,
    "retrieval-bm25": lambda: _retrieval("bm25"),
    "retrieval-dense": lambda: _retrieval("dense"),
    "retrieval-hybrid": lambda: _retrieval("hybrid"),
    "llm": _llm,
}


def get_reviewer(name: str):
    try:
        return REGISTRY[name]()
    except KeyError as exc:
        raise SystemExit(f"unknown reviewer {name!r}; choose from {sorted(REGISTRY)}") from exc
