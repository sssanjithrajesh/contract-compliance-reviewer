# ADR-0002: Hybrid BM25 + local dense retrieval, presence decided by either signal

**Status:** Accepted
**Date:** 2026-09-27
**Deciders:** forward-deployed engineer

## Context

Phase 2 needs a way to find the part of a contract that answers each of the 15 clause
questions, with two hard constraints from discovery: client documents cannot leave the
firm's control (so an offline path must exist), and a missed clause is worse than a false
alarm (a lawyer catches false alarms in the review queue; nobody catches a silent miss).

The keyword baseline scored 62% presence accuracy and hallucinated a clause 61% of the
time when none existed. Anything we ship has to beat that, measurably, with the same
120 cases.

## Options considered

### Option A: Full-document prompting (no retrieval)

Send the whole contract to a large-context model with all 15 questions. Simplest code.
Rejected for this phase: every review costs a full-contract prompt (16k to 70k characters
per contract times 900 contracts a year), there is no offline path without a large local
model, and it gives the eval set nothing to say about *where* the system looked. Kept as
a candidate for a later comparison once an API key is in place.

### Option B: BM25 only

Lexical ranking over paragraph chunks. No model, no download, runs anywhere, and legal
drafting is formulaic ("shall be governed by the laws of") which suits lexical matching.
Measured: 82% presence accuracy, 57% span recall, 11% false refusal, 24% hallucination
at the calibrated threshold.

### Option C: Dense only (local embedding model)

BAAI/bge-small-en-v1.5 via fastembed (ONNX, CPU, ~130 MB, cached after first download).
Catches paraphrase that BM25 misses. Measured alone: worse than BM25 at every threshold
that kept false refusals under 25%; at the threshold where it stops hallucinating it
misses 43% of present clauses. On formulaic legal text, lexical beats semantic.

### Option D: Hybrid, reciprocal rank fusion, presence if either signal clears its bar

Rank with both, fuse with RRF for the citation order, and declare a clause present if
BM25 >= 8.0 **or** cosine >= 0.72. Measured: 82% presence accuracy, 62% span recall,
9% false refusal, 24% hallucination. The dense signal buys five points of recall and two
points fewer misses over BM25 alone, at the cost of the model download and roughly 3
seconds per contract on CPU.

## Decision

Option D. The dense model also **is** the air-gapped path: it never calls out, so the
offline deployment in Phase 3 is a configuration change rather than a rewrite.

Thresholds were chosen by `scripts/calibrate_thresholds.py` with the rule "maximise
presence accuracy subject to false refusal <= 25%", then nudged toward the lower-miss
setting because of the customer's stated priority.

## Consequences

- Easier: the review queue now proposes something worth a lawyer's time on 8 of 10
  contracts, up from 6 of 10, and refuses cleanly 76% of the time when it should.
- Harder: citation precision is 38%. Retrieval cites whole paragraphs (up to 1,200
  characters); the annotated clause is usually one or two sentences inside them. This is
  the job of the LLM extraction step, which is written and tested against a fake client
  but unscored until an API key is available.
- Debt: thresholds were calibrated on the same 120 cases we report. Leave-one-contract-out
  presence accuracy ranged from 67% to 100% (mean 84%), so expect the real number to move
  by several points on new contracts. The firm's approved/rejected findings will recalibrate
  this in Phase 4.
- Ruled out for now: reranking with a cross-encoder. Worth trying when citation precision
  is the bottleneck rather than presence.

## Cost

About five hours including the calibration script and ADR. Runtime: 3 to 4 seconds per
contract for indexing on a laptop CPU, then milliseconds per clause. No API spend.

## Revisit when

- An API key is available and the LLM reviewer is scored: if full-document prompting
  (Option A) beats retrieval + extraction on span recall at acceptable cost, the
  architecture simplifies.
- Scanned contracts enter the eval set: OCR noise hurts BM25 more than dense retrieval,
  which may flip the weighting.
- Citation precision stays below 60% after LLM extraction: add a cross-encoder reranker.
