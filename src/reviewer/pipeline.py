"""The reviewers that matter: retrieval-only and retrieval + LLM extraction.

RetrievalReviewer answers "where in this contract should a lawyer look for clause X?"
It cites the shortest confirming sentences inside the top chunks and refuses when
nothing scores above a threshold or no distinctive phrase is present. No model
reasoning, so it cannot hallucinate content, but it also cannot tell a real
termination-for-convenience clause from a paragraph that merely mentions termination.

LLMReviewer takes the same retrieved chunks and asks a model to decide presence and quote
the exact evidence. Quotes are mapped back to character offsets; anything that is not a
verbatim substring of the contract is dropped. The model never gets to invent a citation.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from reviewer.chunking import chunk_text
from reviewer.clauses import CLAUSE_TYPES
from reviewer.extract import distinctive_hits, sentences_from_text
from reviewer.interfaces import Finding, Span
from reviewer.retrieval import Index, Mode


@dataclass
class RetrievalConfig:
    mode: Mode = "hybrid"
    top_k: int = 5
    cite_top_n: int = 2
    # Presence thresholds, calibrated with scripts/calibrate_thresholds.py (ADR-0002).
    # Present if EITHER signal clears its bar. Chosen to keep false refusals low because a
    # missed clause is the customer's worst outcome; hallucinations are caught in review.
    bm25_min_score: float = 8.0
    dense_min_sim: float = 0.72


def clause_query(clause_type: str) -> str:
    ct = CLAUSE_TYPES[clause_type]
    return f"{ct.question} {' '.join(ct.keywords)}"


class RetrievalReviewer:
    def __init__(self, config: RetrievalConfig | None = None) -> None:
        self.config = config or RetrievalConfig()
        self.name = f"retrieval-{self.config.mode}"
        self._index_cache: dict[int, Index] = {}

    def _index(self, contract_text: str) -> Index:
        key = hash(contract_text)
        if key not in self._index_cache:
            self._index_cache.clear()  # one contract at a time; keep memory flat
            self._index_cache[key] = Index(chunk_text(contract_text), mode=self.config.mode)
        return self._index_cache[key]

    def _present(self, index: Index, query: str) -> tuple[bool, float]:
        """Decide presence from the raw top score of whichever signal is available."""
        cfg = self.config
        if index.mode in ("bm25", "hybrid"):
            top = index._bm25_ranked(query)[0][1]
            if top >= cfg.bm25_min_score:
                return True, min(1.0, top / (cfg.bm25_min_score * 3))
        if index.mode in ("dense", "hybrid"):
            top = index._dense_ranked(query)[0][1]
            if top >= cfg.dense_min_sim:
                return True, float(top)
        return False, 0.0

    def review(self, contract_text: str, clause_type: str, question: str) -> Finding:
        if clause_type not in CLAUSE_TYPES:
            return Finding.absent(rationale=f"unknown clause type {clause_type!r}")
        index = self._index(contract_text)
        query = clause_query(clause_type)
        present, confidence = self._present(index, query)
        if not present:
            return Finding.absent(rationale="no chunk scored above the presence threshold", confidence=0.6)
        hits = index.search(query, k=self.config.top_k)
        sentences: list[Span] = []
        for hit in hits:
            sentences.extend(sentences_from_text(hit.chunk.text, hit.chunk.start))
        phrases = CLAUSE_TYPES[clause_type].confirm_phrases()
        spans = distinctive_hits(sentences, phrases, limit=self.config.cite_top_n)
        if not spans:
            # Retrieval liked a neighbourhood that never actually states the clause
            # (e.g. "terminate for breach" vs "terminate for convenience"). Refuse.
            return Finding.absent(
                rationale="top chunks mention the topic but no distinctive clause phrase",
                confidence=0.55,
            )
        return Finding(
            present=True,
            spans=spans,
            rationale=f"sentence-level evidence in top-{len(hits)} chunks for {clause_type}",
            confidence=confidence,
        )


_SYSTEM = """You are a contract-review assistant for a law firm. You will be given excerpts from
one contract and a question about one clause type. Decide whether the contract contains that
clause, using ONLY the excerpts. If it does, quote the exact sentence(s) that constitute the
clause, verbatim, character for character. Never paraphrase inside a quote. If the excerpts do
not contain the clause, say so. Respond with JSON only:
{"present": true|false, "quotes": ["..."], "reasoning": "one sentence"}"""


class LLMReviewer:
    """Retrieval + model extraction. Requires ANTHROPIC_API_KEY (or a client passed in)."""

    name = "llm"

    def __init__(self, client=None, model: str | None = None, retrieval: RetrievalConfig | None = None):
        self.model = model or os.environ.get("CCR_LLM_MODEL", "claude-sonnet-4-5")
        self.retrieval = RetrievalReviewer(retrieval or RetrievalConfig(top_k=6))
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit("LLMReviewer needs ANTHROPIC_API_KEY set (or pass a client)")
            import anthropic

            client = anthropic.Anthropic()
        self.client = client

    @staticmethod
    def _parse_answer(raw: str) -> dict:
        """Best-effort JSON object. Unparseable output is a refusal, not a crash."""
        start = raw.find("{")
        if start < 0:
            return {"present": False, "quotes": [], "reasoning": "model returned no JSON"}
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw, start)
        except json.JSONDecodeError:
            return {"present": False, "quotes": [], "reasoning": "model JSON was unparseable"}
        if not isinstance(obj, dict):
            return {"present": False, "quotes": [], "reasoning": "model JSON was not an object"}
        return obj

    def _ask(self, question: str, excerpts: list[str]) -> dict:
        joined = "\n\n---\n\n".join(f"[excerpt {i + 1}]\n{e}" for i, e in enumerate(excerpts))
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                system=_SYSTEM,
                messages=[{"role": "user", "content": f"Question: {question}\n\nExcerpts:\n{joined}"}],
            )
        except Exception as exc:  # noqa: BLE001 — eval must finish even if one call fails
            return {"present": False, "quotes": [], "reasoning": f"provider error: {exc.__class__.__name__}"}
        raw = "".join(getattr(b, "text", "") for b in response.content)
        return self._parse_answer(raw)

    @staticmethod
    def _ground(quotes: list[str], contract_text: str) -> list[Span]:
        spans: list[Span] = []
        for q in quotes:
            q = q.strip()
            if len(q) < 10:
                continue
            start = contract_text.find(q)
            if start < 0:
                # tolerate whitespace differences
                pattern = r"\s+".join(map(re.escape, q.split()))
                m = re.search(pattern, contract_text)
                if not m:
                    continue
                start, end = m.start(), m.end()
            else:
                end = start + len(q)
            spans.append(Span(start=start, end=end, text=contract_text[start:end]))
        return spans

    def review(self, contract_text: str, clause_type: str, question: str) -> Finding:
        if clause_type not in CLAUSE_TYPES:
            return Finding.absent(rationale=f"unknown clause type {clause_type!r}")
        index = self.retrieval._index(contract_text)
        hits = index.search(clause_query(clause_type), k=self.retrieval.config.top_k)
        answer = self._ask(question, [h.chunk.text for h in hits])
        spans = self._ground(answer.get("quotes") or [], contract_text) if answer.get("present") else []
        if not spans:
            # Either the model said absent, or it said present but could not quote real text.
            return Finding.absent(
                rationale=answer.get("reasoning", "") or "model found no verbatim evidence",
                confidence=0.7,
            )
        return Finding(present=True, spans=spans, rationale=answer.get("reasoning", ""), confidence=0.8)
