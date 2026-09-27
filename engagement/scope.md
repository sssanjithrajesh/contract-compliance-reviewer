# Scope: Contract Compliance Reviewer for Harlow & Pryce LLP

**Version:** 1.0, 2026-09-26
**Engagement length:** 8 weeks, four two-week phases
**Customer:** fictional; see [discovery-memo.md](discovery-memo.md)

## In scope

1. **Clause-level review** of the firm's 15 checklist items on uploaded contracts (PDF,
   scanned PDF, DOCX). For each item: cited text with page and character span, or an
   explicit "not found".
2. **Human review queue.** Every finding is proposed, not final, until a named user
   approves or rejects it. Rejections are recorded and feed the eval set.
3. **Measured accuracy.** An eval set built from CUAD, scored before the system is built
   and re-scored on every change. The firm gets a number for miss rate and hallucination
   rate before pilot.
4. **Integrations via MCP:** the firm's HubSpot-based practice-management system
   (read matter and client, write findings back) and Slack (notify the assigned reviewer).
   Each integration degrades gracefully: if HubSpot is down, review still works and
   write-back queues.
5. **Deployment options:** Docker Compose for the pilot; Helm chart for the firm's cloud
   tenancy; an offline mode that swaps the hosted model for a local one with a single flag.
6. **Engagement deliverables:** this scope, the discovery memo, an architecture decision
   record for each significant choice, a runbook, a post-mortem of the first production
   incident, and a three-minute demo.

## Out of scope (this engagement)

- Drafting, redlining, or suggesting alternative language.
- Risk scoring or advice beyond "this clause exists and here it is".
- Integration with the document management system (iManage).
- Clause types beyond the 15 on the checklist. Adding one is a config change, not a
  scope change, but it is not promised here.
- Languages other than English.
- Fine-tuning a model. Retrieval, prompting, and evals first; fine-tuning only if the
  eval set proves it necessary.

## Phases and exit criteria

| Phase | Weeks | Ships | Exit criterion |
|---|---|---|---|
| 1 Spec | 1-2 | Eval set (100+ cases), harness, CI gate, baseline number, this document | Baseline scorecard published; firm agrees the 15 questions are the right ones |
| 2 Core | 3-4 | Retrieval + extraction with citations, refusal path, review queue, web UI | Span recall >= 80%, hallucinated presence <= 10% on the eval set |
| 3 Integrate | 5-6 | MCP servers for HubSpot + Slack, Docker Compose, offline mode | Findings visible on a matter record; each integration's failure mode documented |
| 4 Harden | 7-8 | Public deploy, runbook, post-mortem, demo, second-customer config | Pilot on 20 real matters with senior verification; miss rate reported |

## Definition of done

The engagement is done when all of the following are true:

- [ ] A junior associate can upload a contract and receive 15 findings, each cited or refused.
- [ ] Every finding passes through the review queue and carries the approving lawyer's name.
- [ ] The eval scorecard shows span recall >= 80% and hallucinated presence <= 10%,
      with the CI gate enforcing no regression.
- [ ] Approved findings appear on the HubSpot matter record within one minute, and
      queue rather than fail when HubSpot is unavailable.
- [ ] The offline flag produces a working review with no outbound network calls
      (verified by packet capture during the demo).
- [ ] The runbook lets the firm's IT lead redeploy and roll back without the engineer.
- [ ] A post-mortem exists for at least one real incident.

## ROI framing (for the managing partner)

Today: ~3.6 junior hours and ~0.8 senior hours per contract, ~900 contracts a year.

Target after pilot: junior time falls to ~1.2 hours (reviewing proposed findings rather
than hunting), senior time to ~0.5 hours (aimed at low-confidence items). That is roughly
2,150 junior hours and 270 senior hours a year returned to billable or higher-value work.

The number the partner actually cares about is not hours. It is the two missed clauses
from last year. The eval set's `false_refusal_rate` is the direct measure of that risk,
and it is reported on every change.

## Assumptions and risks

- **Assumption:** CUAD's clause categories match the firm's checklist closely enough that
  the public benchmark is a fair proxy. Confirmed for 15 of 15 in discovery.
- **Assumption:** the firm can provision a HubSpot developer account and Slack workspace for the
  pilot within week 3.
- **Risk:** scanned contracts. OCR quality drives everything downstream. Mitigation: the
  eval set will include generated scans (rotated, low-DPI) in phase 2, scored separately.
- **Risk:** offline mode uses a smaller model and will score lower. It will have its own
  line on the scorecard rather than being hidden in the average.
- **Risk:** the eval set is small (120 cases). It is large enough to catch regressions,
  not to certify. Phase 4 adds the firm's own approved/rejected findings to it.
