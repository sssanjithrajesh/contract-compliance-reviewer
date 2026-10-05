"""Turn retrieved chunks into the shortest citeable sentences.

Retrieval finds the right neighbourhood. Citation precision is scored on character
overlap with the expert span, so quoting a 1,200-character paragraph around a
40-character clause looks like a miss. This module is the cheap, offline stand-in
for LLM extraction: split on sentence boundaries, keep only sentences that carry a
clause-specific phrase, prefer the shortest hit.
"""

from __future__ import annotations

import re

from reviewer.interfaces import Span

_SENTENCE = re.compile(r"(?<=[.;:])\s+")


def sentences_from_text(text: str, origin: int = 0) -> list[Span]:
    """Split `text` into sentence spans whose offsets are relative to the full contract."""
    if not text:
        return []
    bounds = [0] + [m.end() for m in _SENTENCE.finditer(text)] + [len(text)]
    out: list[Span] = []
    for a, b in zip(bounds, bounds[1:], strict=False):
        raw = text[a:b]
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        if b - trail <= a + lead:
            continue
        start, end = origin + a + lead, origin + b - trail
        out.append(Span(start=start, end=end, text=text[a + lead : b - trail]))
    return out


def distinctive_hits(sentences: list[Span], phrases: tuple[str, ...], limit: int = 2) -> list[Span]:
    """Keep sentences that contain at least one confirm phrase, shortest first."""
    scored: list[tuple[int, int, Span]] = []
    lowered_phrases = [p.lower() for p in phrases if p]
    for s in sentences:
        window = s.text.lower()
        n = sum(1 for p in lowered_phrases if p in window)
        if n:
            scored.append((-n, len(s), s))
    scored.sort(key=lambda t: (t[0], t[1], t[2].start))
    seen: set[tuple[int, int]] = set()
    out: list[Span] = []
    for _, __, s in scored:
        key = (s.start, s.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out
