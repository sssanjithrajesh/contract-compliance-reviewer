# ADR-0001: Build the eval set before the system, from CUAD, including absent cases

**Status:** Accepted
**Date:** 2026-09-26
**Deciders:** forward-deployed engineer, with the customer's practice head on the clause list

## Context

The customer's two worst incidents were missed clauses, not misread ones
([discovery memo](../../engagement/discovery-memo.md), section 3). The managing partner's
condition for rollout is a measured error rate. That means the measurement has to exist
before there is anything to measure, and it has to include the case where the right
answer is "this clause is not here".

We had two weeks for phase 1 and no access to the firm's own contracts yet.

## Options considered

### Option A: Hand-write 30 to 50 cases against a few sample contracts

Cheapest to start. We control the questions exactly. Fails because 30 to 50 cases is too
few to distinguish a 5% miss rate from a 15% one, the annotations would be ours (no
independent ground truth), and there is no public number to compare against.

### Option B: Use CUAD (Contract Understanding Atticus Dataset)

510 contracts, 41 clause categories, ~13,000 expert-annotated spans with character offsets,
CC-BY 4.0. Fifteen of the categories map directly onto the firm's checklist. Every
category is annotated for every contract, so absent cases come for free and are
authoritative (a lawyer looked and did not find it). Published models report on it, so
"we score X" means something outside this engagement. Cost: the contracts are US SEC
filings, older and more formal than the firm's typical intake, and none are scanned.

### Option C: LegalBench or ContractNLI

Broader legal reasoning benchmarks. LegalBench is task-oriented and does not give clause
spans in full contracts. ContractNLI gives entailment over NDAs only. Neither measures
"find the clause and cite it", which is the job.

### Option D: Wait for the firm's own contracts and annotate those

Most representative. Fails the two-week window: the firm cannot release client documents
until the offline deployment exists (phase 3), and annotation by their associates would
cost billable hours before there is any tool to show for it.

## Decision

Option B now, with Option D layered in during phase 4 when approved/rejected findings from
real matters flow back into the eval set.

Specifics:

- 8 contracts, 15 clause types, 120 cases, deterministic sample (seed committed).
- Roughly 45% present / 55% absent. Absent cases test refusal, which is the behaviour
  the customer cares about most.
- Contracts chosen across agreement kinds (agency, supply, co-branding, consulting,
  development, endorsement, cooperation, master services) so the set is not one genre.
- Every span verified against the contract text on load; a drifted case fails tests.
- Five metrics, each phrased as a question a lawyer would ask (see `evals/scoring.py`).
- A regression gate in CI with the current numbers as the floor.

## Consequences

- Easier: every later change has a number attached. Arguments about "is it better" are
  settled by `uv run ccr-eval`.
- Easier: the keyword baseline was scored in the first hour. It hallucinates a clause 61%
  of the time when none exists. That number is now the story's starting point.
- Harder: CUAD contracts are clean text. Scanned-document performance is unmeasured until
  we generate degraded PDFs in phase 2. This is a known gap, tracked in scope.md.
- Debt: 120 cases is enough to catch regressions, not to certify accuracy. The gate
  tolerance is set to one percentage point, which is roughly one case; noise is real.
- Ruled out: nothing. The schema accepts `dataset: manual` and `synthetic` sources.

## Cost

About six hours: dataset inspection, schema, build script, scoring, report, tests, and
this record. No compute cost; the baseline runs in under a second.

## Revisit when

- The firm's own approved/rejected findings exceed ~100, at which point they should
  become the primary set and CUAD the secondary.
- Span recall on CUAD exceeds 90% while the firm still reports misses. That would mean
  CUAD has stopped being representative and the set needs harder, messier cases.
