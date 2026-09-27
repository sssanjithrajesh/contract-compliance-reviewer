# Architecture Decision Records

One file per significant decision. Each records the options that were seriously
considered, not just the winner, what the choice cost, and what would make us revisit it.

| ADR | Decision | Status |
|---|---|---|
| [0000](0000-template.md) | Template | - |
| [0001](0001-eval-set-before-system.md) | Build the eval set before the system, from CUAD, with absent cases | Accepted |
| [0002](0002-retrieval-architecture.md) | Hybrid BM25 + local dense retrieval; presence if either signal clears its bar | Accepted |

Upcoming: LLM extraction prompt and grounding policy, integration transport (MCP vs
direct SDK), offline model choice, storage (SQLite pilot vs Postgres/pgvector).
