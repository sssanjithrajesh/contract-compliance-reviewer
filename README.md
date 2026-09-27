# Contract Compliance Reviewer

**An eval-first, citation-only contract review system, built as a full customer engagement for a fictional mid-size law firm.**

A lawyer uploads a messy contract. The system answers fifteen questions a partner would ask
("Which law governs this?", "Can they walk away without cause?", "Is liability capped?")
and for every answer it either points at the exact text in the document or says
**"not found"**. Nothing gets marked final without a human reviewer signing off.

> Status: **Phase 2 of 4 - working reviewer with human review queue.** Retrieval runs
> fully offline on a local model. LLM extraction is built and tested but unscored until
> an API key is available. Every number below is produced by `uv run ccr-eval` and
> committed; nothing is hand-typed.

![Eval scorecard](docs/img/scorecard.svg)

### Progression so far

| Version | Presence accuracy | Span recall | Citation precision | False refusal | Hallucinated presence |
|---|---:|---:|---:|---:|---:|
| Keyword baseline (Phase 1) | 62% | 35% | 17% | 9% | **61%** |
| Retrieval, BM25 only | 82% | 57% | 36% | 11% | 24% |
| **Retrieval, hybrid (current)** | **82%** | **62%** | **38%** | **9%** | **24%** |
| Retrieval + LLM extraction | pending API key | | | | |

Citation precision is the known weak spot: retrieval cites whole paragraphs, the
annotated clause is one or two sentences inside them. That is the LLM extraction step's
job ([ADR-0002](docs/adr/0002-retrieval-architecture.md) explains the tradeoff).

Full per-clause table: [docs/scorecard.md](docs/scorecard.md).

### The review queue

![Review queue for one contract](docs/img/review-queue.png)

Every finding is either cited to a page and character range or marked "not found".
Nothing is final until a named person approves or rejects it; the decision, name, and
note are stored and exported with the review.

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

Built so far: Ingest (PDF/DOCX/TXT with page map), hybrid retrieval, refusal path,
human review queue with audit trail, the Evals box, and the interfaces the remaining
boxes must satisfy. LLM extraction is wired and tested behind an API key. MCP
integrations are Phase 3.

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
uv run pytest                            # unit, app, and eval-set integrity tests
uv run ccr-serve                         # review queue at http://127.0.0.1:8000
uv run ccr-eval                          # score the production reviewer, regenerate chart + table
uv run ccr-eval --reviewer keyword       # or: retrieval-bm25, retrieval-dense, retrieval-hybrid, llm
uv run ccr-eval --gate                   # what CI runs: fail on regression vs evals/gate.json
uv run ccr-build-evals                   # rebuild the eval set from CUAD (deterministic seed)
uv run python -m scripts.calibrate_thresholds   # the sweep behind ADR-0002
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). The embedding model
(~130 MB) downloads once and is cached; after that nothing leaves the machine.
`--reviewer llm` needs `ANTHROPIC_API_KEY`. Set `CCR_REVIEWER` to choose the engine the
web app runs on upload, and `DATABASE_URL` to point at Postgres instead of the default SQLite.

## Repository map

```
src/reviewer/        the system under test
  interfaces.py        Finding / Span / Reviewer protocol - the contract every version honours
  clauses.py           the 15 clause types, their plain-English questions, and why each matters
  baselines.py         keyword baseline (the floor), always-absent (sanity), and the reviewer registry
  ingest.py            PDF / DOCX / TXT to text + page map; detects scans with no text layer
  chunking.py          paragraph-aware chunks that keep character offsets
  retrieval.py         BM25, local dense (bge-small via fastembed), and RRF hybrid
  pipeline.py          RetrievalReviewer (offline) and LLMReviewer (grounded quotes only)
  app/                 FastAPI review queue: upload, propose, approve/reject, export
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
| 1 (done) | Eval set, harness, CI gate, interfaces, engagement docs | Baseline row in the progression table |
| 2 (now) | Ingest, hybrid retrieval, refusal, human-review queue, LLM extraction (behind key) | Scorecard climbed 62% to 82% presence, 61% to 24% hallucination; ADR-0002 |
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
