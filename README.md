# Contract Compliance Reviewer

**Type:** Anchor engagement (6–8 weeks). Fictional customer: a mid-size law firm.
**Target roles:** Legal-vertical AI startups (Harvey, Hebbia), Solutions / Applied AI Engineer at labs, FDE on-ramp.

Upload messy contracts (CUAD dataset plus generated scanned/rotated PDFs), get clause-level
findings with page/span citations, refusal when unsupported, and a human-review queue before
anything is marked final.

## Deliverables

- Eval set (100+ cases, built before the system) scored on LegalBenchRAG; CI gate blocks regressions
- Hybrid retrieval + reranking, FastAPI + Postgres/pgvector
- MCP servers: document store, HubSpot/Salesforce (matter records, write-back), Slack notifications
- Sub-agents: clause extractor, obligation checker, risk summarizer; packaged "contract review" skill
- Deployment: Docker Compose, Helm/Terraform for customer VPC, air-gapped mode, OIDC login
- Architecture Decision Record, post-mortem, discovery memo, scope doc, runbook, 3-minute demo
- Second customer config: healthcare policy reviewer (Synthea + public FHIR sandbox)

## Status

Not started. First task: eval-case schema and discovery memo.
