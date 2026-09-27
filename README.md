# Contract Compliance Reviewer

**An eval-first, citation-only contract review system, built as a full customer engagement for a fictional mid-size law firm.**

A lawyer uploads a messy contract. The system answers fifteen questions a partner would ask
("Which law governs this?", "Can they walk away without cause?", "Is liability capped?")
and for every answer it either points at the exact text in the document or says
**"not found"**. Nothing gets marked final without a human reviewer signing off.

> Status: **Phase 1 of 4 - eval set and harness.** The number below is a deliberately
> dumb keyword baseline. It is the floor every later version has to beat, in public.

![Eval scorecard](docs/img/scorecard.svg)

Full per-clause table: [docs/scorecard.md](docs/scorecard.md). Regenerated on every run of `uv run ccr-eval`.

---

## Why this project exists

Most "AI contract review" demos fail in the same three ways when a real firm tries them:
they invent clauses that are not there, they cite the wrong paragraph, and nobody can
say how often either happens. This project is built around measuring those failures
before writing the system that has to avoid them.

Concretely:

| The firm's question | How this repo answers it |
|---|---|
| "How often does it make things up?" | `hallucinated_presence_rate` on 60+ clauses that are genuinely absent |
| "When it cites something, is that real?" | `citation_precision`: every cited span must overlap annotated evidence |
| "Does it find what a lawyer would find?" | `span_recall` against the CUAD expert annotations |
| "Will it get worse after an update?" | CI regression gate blocks merges below the committed floor |
| "Can we run it inside our own network?" | Planned: air-gapped mode swaps the model with one flag (Phase 3) |

## Architecture (target state)

```mermaid
flowchart LR
    subgraph Ingest
        U[Upload PDF / scan] --> P[Parse + OCR]
        P --> C[Chunk + embed]
        C --> V[(Postgres / pgvector)]
    end

    subgraph Review
        Q[15 clause questions] --> R[Hybrid retrieval<br/>BM25 + vector + rerank]
        V --> R
        R --> E[Clause extractor]
        E --> O[Obligation checker]
        O --> S[Risk summarizer]
        S --> F{Grounded?}
        F -- yes --> H[Human review queue]
        F -- no --> N["Not found" refusal]
    end

    subgraph Integrations via MCP
        H --> CRM[HubSpot / Salesforce<br/>matter record write-back]
        H --> SL[Slack notification]
    end

    subgraph Evals
        EV[120 CUAD cases] -.scores.-> E
        EV -.CI gate.-> CI[GitHub Actions]
    end
```

Phase 1 (this commit) is the **Evals** box plus the interfaces every other box must satisfy.

## The eval set is the spec

120 cases across 8 real contracts and 15 clause types, derived from
[CUAD](https://www.atticusprojectai.org/cuad) (expert-annotated, CC-BY 4.0).
About half are **absent** cases: the clause is not in the contract and the correct answer
is a refusal. Those are the cases that distinguish a useful tool from a confident liar.

```yaml
# evals/cases/<contract>.yaml (one case shown)
- id: biopurecorp-agency-agreement__governing_law
  clause_type: governing_law
  question: Which jurisdiction's law governs this contract?
  expected:
    present: true
    spans:
      - start: 33184
        end: 33448
        text: This Agreement and all related business transactions will be governed by the laws of the C...
  source: {dataset: cuad, id: "BIOPURECORP_06_30_1999-EX-10.13-AGENCY AGREEMENT__Governing Law"}
  tags: [present]
```

Every span is verified against the contract text on load. A case that drifts from its
document fails the test suite.

### Metrics

| Metric | Question it answers | Direction |
|---|---|---|
| `presence_accuracy` | Did it correctly say whether the clause exists? | higher |
| `span_recall` | When present, did it find the actual text (>= 50% coverage)? | higher |
| `citation_precision` | Of everything it cited, how much overlapped real evidence? | higher |
| `false_refusal_rate` | How often did it say "not found" when the clause was there? | lower |
| `hallucinated_presence_rate` | How often did it claim a clause that does not exist? | lower |

## Run it

```bash
uv sync --extra dev
uv run pytest                       # schema, scoring, and eval-set integrity tests
uv run ccr-eval                     # score the keyword baseline, regenerate chart + table
uv run ccr-eval --gate              # what CI runs: fail on regression vs evals/gate.json
uv run ccr-build-evals              # rebuild the eval set from CUAD (deterministic seed)
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). No API keys needed for Phase 1.

## Repository map

```
src/reviewer/        the system under test
  interfaces.py        Finding / Span / Reviewer protocol - the contract every version honours
  clauses.py           the 15 clause types, their plain-English questions, and why each matters
  baselines.py         keyword baseline (the floor) and always-absent (harness sanity check)
evals/
  schema.py            eval case format, loader, span verification
  scoring.py           the five metrics
  report.py            terminal table, Markdown table, SVG chart (no matplotlib)
  run.py               CLI + CI regression gate
  cases/*.yaml         120 cases, one file per contract
  contracts/*.txt      the 8 contract texts (CUAD, CC-BY 4.0)
  gate.json            the regression floor CI enforces
engagement/          what a real engagement produces besides code
  discovery-memo.md    who the customer is, what they do today, what "better" means
  scope.md             what is in, what is out, what "done" means, and the ROI framing
docs/
  adr/                 architecture decision records (options considered, not just the winner)
  scorecard.md         current numbers, regenerated by ccr-eval
  img/scorecard.svg    the chart above
```

## Roadmap

| Phase | Deliverable | Proof |
|---|---|---|
| 1 (now) | Eval set, harness, CI gate, interfaces, engagement docs | This README's chart |
| 2 | Hybrid retrieval + reranking + LLM extraction with citations, human-review queue, FastAPI + React | Scorecard climbs from baseline; ADR-001 retrieval choice |
| 3 | MCP servers (document store, HubSpot, Slack), sub-agents, packaged review skill, Docker Compose, air-gapped flag | Integration write-up: what broke and how it degrades |
| 4 | Public deploy, post-mortem, runbook, 3-min demo, second customer (healthcare policy reviewer via config) | Same codebase, different YAML, different domain |

## Engagement documents

- [Discovery memo](engagement/discovery-memo.md): the customer, their current process, and where the hours go.
- [Scope](engagement/scope.md): what ships, what does not, and how success is measured.
- [Architecture decisions](docs/adr/): every significant choice with the alternatives that lost.

## Data and licensing

Contract texts and clause annotations come from the
[Contract Understanding Atticus Dataset (CUAD)](https://github.com/TheAtticusProject/cuad),
Hendrycks et al., 2021, licensed CC-BY 4.0. See [ATTRIBUTION.md](ATTRIBUTION.md).
Code is MIT.
