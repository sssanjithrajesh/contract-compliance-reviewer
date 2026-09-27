"""Split contract text into retrieval units that keep their character offsets.

Contracts are structured: numbered sections, sub-clauses, defined terms in capitals. A
chunker that respects paragraph boundaries retrieves better than fixed windows and, more
importantly, produces spans a lawyer recognises as "the clause" rather than a fragment.

Paragraphs longer than `max_chars` are split on sentence boundaries with overlap so a
clause that straddles a boundary is still recoverable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from reviewer.interfaces import Span

_PARAGRAPH = re.compile(r"\n\s*\n+")
_SENTENCE = re.compile(r"(?<=[.;:])\s+")


@dataclass(frozen=True)
class Chunk:
    index: int
    start: int
    end: int
    text: str

    def as_span(self) -> Span:
        return Span(start=self.start, end=self.end, text=self.text)


def _split_long(start: int, text: str, max_chars: int, overlap: int) -> list[tuple[int, int]]:
    """Split one long paragraph into (start, end) windows on sentence boundaries."""
    boundaries = [0] + [m.end() for m in _SENTENCE.finditer(text)] + [len(text)]
    windows: list[tuple[int, int]] = []
    win_start = 0
    while win_start < len(text):
        # advance to the last boundary that keeps the window under max_chars
        candidates = [b for b in boundaries if win_start < b <= win_start + max_chars]
        win_end = candidates[-1] if candidates else min(len(text), win_start + max_chars)
        windows.append((start + win_start, start + win_end))
        if win_end >= len(text):
            break
        # step back for overlap, but always make progress
        back = [b for b in boundaries if win_end - overlap <= b < win_end]
        win_start = back[0] if back and back[0] > win_start else win_end
    return windows


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150, min_chars: int = 40) -> list[Chunk]:
    chunks: list[Chunk] = []
    pos = 0
    for match in list(_PARAGRAPH.finditer(text)) + [None]:
        end = match.start() if match else len(text)
        para = text[pos:end]
        if para.strip():
            lead = len(para) - len(para.lstrip())
            trail = len(para) - len(para.rstrip())
            p_start, p_end = pos + lead, end - trail
            if p_end - p_start <= max_chars:
                windows = [(p_start, p_end)]
            else:
                windows = _split_long(p_start, text[p_start:p_end], max_chars, overlap)
            for s, e in windows:
                if e - s >= min_chars:
                    chunks.append(Chunk(index=len(chunks), start=s, end=e, text=text[s:e]))
        pos = match.end() if match else end
    return chunks
