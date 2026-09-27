# Risk triage for the partner summary

Implemented in `RiskSummarizer` (`src/reviewer/agents.py`). Rule-based so it runs
offline; an LLM, when available, only rewrites the wording and may not add or remove items.

## Severity rules

| Situation | Severity | Reason |
|---|---|---|
| Uncapped liability, non-compete, exclusivity, change of control **found** | high | Each can materially change the client's exposure or options |
| Liability cap **not found** | high | The absence is the exposure |
| Liquidated damages, MFN, minimum commitment, termination for convenience, IP assignment **found** | medium | Cost or flexibility items a partner should see |
| Governing law, insurance, anti-assignment **not found** | medium | Usually an oversight worth confirming |
| Anything else found | low | Routine |
| Anything else not found | low | No action |

Within a severity band, higher-confidence findings come first.

## Summary shape

One line of counts, then high items, then up to four medium items, then the first
dated obligation if any, then the fixed sentence:

> All items are proposals pending a named lawyer's approval.

That sentence is a contract with the reader. The LLM rewrite step is instructed to keep
it verbatim and the fallback path guarantees it.
