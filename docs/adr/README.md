# Architecture Decision Records

One file per significant decision. Each records the options that were seriously
considered, not just the winner, what the choice cost, and what would make us revisit it.

| ADR | Decision | Status |
|---|---|---|
| [0000](0000-template.md) | Template | - |
| [0001](0001-eval-set-before-system.md) | Build the eval set before the system, from CUAD, with absent cases | Accepted |
| [0002](0002-retrieval-architecture.md) | Hybrid BM25 + local dense retrieval; presence if either signal clears its bar | Accepted |
| [0003](0003-outbox-and-mcp-boundaries.md) | Integrations via a transactional outbox; MCP servers split by trust boundary | Accepted |
| [0004](0004-second-customer-by-config.md) | Second customer via YAML + clause data; per-customer scorecards; identity from the SSO proxy | Accepted |
| [0005](0005-sentence-citations-and-salesforce.md) | Sentence-level citations with distinctive-phrase confirmation; Salesforce as a second CRM | Accepted |

Upcoming: LLM extraction scoring once a key is available, proxy-supplied roles for MCP,
"present but deficient" as a third finding state, OCR for scanned intake.
