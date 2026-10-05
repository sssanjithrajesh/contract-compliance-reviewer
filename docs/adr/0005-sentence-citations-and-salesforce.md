# ADR-0005: Sentence-level citations + Salesforce as a second CRM

**Status:** Accepted
**Date:** 2026-10-04
**Deciders:** forward-deployed engineer

## Context

Phase 4 shipped a working engagement, but the numbers contradicted the demo script.
The demo says "it does not make things up." The scored hybrid engine invented a
clause 24% of the time and only 38% of citations overlapped the expert span. The
cause was documented in ADR-0002: we cited whole retrieved paragraphs, and presence
fired if BM25 *or* dense cleared a bar, so a paragraph that merely said "terminate"
looked like Termination for Convenience.

Separately, every FDE posting we are targeting (Anthropic MCP deliverable, Glean
interview "Salesforce + Slack + HR, make it safe") treats a second system of record
as table stakes. We had HubSpot only.

## Options considered

### Option A: Wait for LLM extraction

The pipeline already maps verbatim quotes back to offsets. That is the right long-term
fix for citation precision. Rejected as the *only* move: it is unmeasured without a
key, and it does not stop the retrieval engine from claiming presence on a weak match
before the model is even called.

### Option B: Cite sentences + require a distinctive phrase

Split the top chunks on sentence boundaries. Keep a sentence only if it contains a
clause-specific confirm phrase (`for convenience`, not just `terminate`). If retrieval
liked the neighbourhood but no sentence confirms the clause, refuse. No API key.
Cost: more false refusals on clauses drafted with unusual wording.

### Option C: Raise the retrieval thresholds globally

Would cut hallucinations and also miss more real clauses. We already calibrated
thresholds to keep false refusals under 25% (ADR-0002). A global raise fights the
customer's stated priority (missed clause worse than a false alarm).

## Decision

Option B for citations and presence confirmation. Keep the hybrid retriever and the
existing thresholds. Add Salesforce as a second CRM adapter with the same three
methods (lookup, write-back, reconcile) and the same outbox/idempotency rules.

What we gave up: recall on clauses whose gold span never uses our confirm phrases.
That will show up as false refusals on the scorecard. We will not hide it.

What we would revisit: if false refusal rises above 20% overall, add per-clause
confirm phrases from the missed gold spans rather than loosening the rule. Once an
API key exists, score `llm` on the same 120 cases and keep whichever engine wins
on hallucination and citation precision.

## Consequences

- `RetrievalReviewer` cites 1–2 sentences, not paragraphs.
- `ClauseType.confirm` is the anti-hallucination list; `keywords` still feed retrieval.
- `integrations.crm.provider: salesforce` is a real path.
- The regression gate may need a one-time update after the first scored run of this
  change, because citation precision and hallucination should move a lot.
