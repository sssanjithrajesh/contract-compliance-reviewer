### LLM extraction — scored

Same 120 CUAD cases as the local hybrid engine. Quotes must be verbatim
substrings or they are dropped.

| Engine | Presence | Span recall | Citation prec | False refusal | Hallucinated |
|---|---:|---:|---:|---:|---:|
| retrieval-hybrid (default) | 85% | 35% | 55% | 30% | **3%** |
| llm | 86% | 55% | **85%** | 20% | 9% |

Decision: keep hybrid as the production default. The buyer's first question is
"how often does it invent a clause?" Hybrid wins that. Use `CCR_REVIEWER=llm`
when they ask for tighter highlights and accept a higher invention rate.

Per-clause LLM table: [scorecard-llm.md](scorecard-llm.md).
