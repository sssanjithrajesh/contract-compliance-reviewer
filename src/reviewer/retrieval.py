"""Find the chunks most likely to contain a given clause.

Three modes, so the eval set can settle the argument rather than opinion (ADR-0002):

- bm25    lexical. Fast, no model, strong on legal boilerplate ("governed by the laws of").
- dense   local embedding model (BAAI/bge-small-en-v1.5 via fastembed, ONNX, runs on CPU,
          no network after the first download). Catches paraphrase.
- hybrid  reciprocal rank fusion of both.

The dense model is local by design: it is the same path the air-gapped deployment uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from reviewer.chunking import Chunk

Mode = Literal["bm25", "dense", "hybrid"]
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_STOP = frozenset(
    "the a an and or of to in for by with on at as is are be this that shall will may any "
    "such its it their his her party parties agreement hereof herein thereof under".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    rank: int


@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")


def _cosine_matrix(query: list[float], docs: list[list[float]]) -> list[float]:
    import math

    qn = math.sqrt(sum(x * x for x in query)) or 1.0
    out = []
    for d in docs:
        dn = math.sqrt(sum(x * x for x in d)) or 1.0
        out.append(sum(a * b for a, b in zip(query, d, strict=True)) / (qn * dn))
    return out


class Index:
    """Per-document index. Built once per contract, queried once per clause type."""

    def __init__(self, chunks: list[Chunk], mode: Mode = "hybrid") -> None:
        if not chunks:
            raise ValueError("cannot index an empty document")
        self.chunks = chunks
        self.mode = mode
        self._bm25 = None
        self._dense: list[list[float]] | None = None
        if mode in ("bm25", "hybrid"):
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi([tokenize(c.text) for c in chunks])
        if mode in ("dense", "hybrid"):
            self._dense = [list(map(float, v)) for v in _embedder().embed([c.text for c in chunks])]

    def _bm25_ranked(self, query: str) -> list[tuple[int, float]]:
        scores = self._bm25.get_scores(tokenize(query))
        return sorted(enumerate(scores), key=lambda kv: kv[1], reverse=True)

    def _dense_ranked(self, query: str) -> list[tuple[int, float]]:
        qv = list(map(float, next(iter(_embedder().embed([query])))))
        sims = _cosine_matrix(qv, self._dense)
        return sorted(enumerate(sims), key=lambda kv: kv[1], reverse=True)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        if self.mode == "bm25":
            ranked = self._bm25_ranked(query)
        elif self.mode == "dense":
            ranked = self._dense_ranked(query)
        else:
            ranked = self._rrf(self._bm25_ranked(query), self._dense_ranked(query))
        return [
            Hit(chunk=self.chunks[i], score=float(s), rank=r)
            for r, (i, s) in enumerate(ranked[:k], start=1)
        ]

    @staticmethod
    def _rrf(*rankings: list[tuple[int, float]], k: int = 60) -> list[tuple[int, float]]:
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, (idx, _) in enumerate(ranking, start=1):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
        return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
