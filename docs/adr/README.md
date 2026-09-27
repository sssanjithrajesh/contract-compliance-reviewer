# Architecture Decision Records

One file per significant decision. Each records the options that were seriously
considered, not just the winner, what the choice cost, and what would make us revisit it.

| ADR | Decision | Status |
|---|---|---|
| [0000](0000-template.md) | Template | - |
| [0001](0001-eval-set-before-system.md) | Build the eval set before the system, from CUAD, with absent cases | Accepted |

Upcoming: retrieval architecture (BM25 vs vector vs hybrid vs full-document prompting),
citation representation (character spans vs page/paragraph), refusal threshold policy,
integration transport (MCP vs direct SDK).
