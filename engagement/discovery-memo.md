# Discovery Memo: Harlow & Pryce LLP (fictional)

**Date:** 2026-09-26
**Prepared by:** Forward-deployed engineer
**Audience:** Firm managing partner, head of commercial practice, IT lead

> Harlow & Pryce is a fictional customer. Its size, process, and numbers are modelled on
> publicly described mid-size commercial practices so the engagement is realistic without
> using anyone's confidential information.

## 1. Who the customer is

Mid-size commercial law firm. About 60 fee-earners, 14 in the commercial contracts
group. Reviews roughly 900 inbound third-party contracts a year for clients: supply,
distribution, licensing, services, sponsorship, and endorsement agreements. Most arrive as
PDFs, a meaningful minority as scans or photographs of signed paper.

The firm has no data science function. IT is two people who manage a document management
system (iManage), Microsoft 365, and a practice-management system that holds matter and
client records. They are cautious about client data leaving their tenancy.

## 2. What happens today

A junior associate opens the contract and works through the firm's 15-point checklist:
governing law, termination rights, liability cap and carve-outs, non-compete, exclusivity,
assignment, change of control, IP ownership, audit rights, insurance, renewal, minimum
commitment, liquidated damages, MFN. For each point they either paste the relevant clause
into a review memo with a page reference, or write "none found".

A senior associate then checks the memo against the contract. In practice the check is
uneven: the senior mostly re-reads the sections the junior flagged and trusts the
"none found" entries.

**Where the hours go (from three interviews and a sample of 20 recent matters):**

| Step | Junior time | Senior time |
|---|---|---|
| Locate and read the 15 clause areas | 2.5 h | - |
| Write the memo with page references | 1.0 h | - |
| Senior verification | - | 0.75 h |
| Rework after senior finds a miss | 0.5 h (about 1 in 4 matters) | 0.25 h |
| **Per contract (weighted)** | **~3.6 h** | **~0.8 h** |

At ~900 contracts a year that is roughly 3,300 junior hours and 700 senior hours.

## 3. What hurts

1. **Misses are silent.** "None found" is the most common error and the hardest to catch.
   The two incidents the practice head raised were both missed clauses (an auto-renewal
   and an uncapped indemnity), not misread ones.
2. **Scanned contracts take twice as long** and are where most of the misses happen.
3. **Consistency across associates is poor.** The same clause gets flagged by one reviewer
   and not another. Clients notice when memos from the same firm differ in rigour.
4. **The memo is disconnected from the matter record.** Findings live in a Word file; the
   practice-management system has no structured view of, say, every client contract with
   an auto-renewal due in the next 90 days.

## 4. What "better" means to them, in their words

- "I want to trust the 'none found' entries." (practice head)
- "Show me the clause on the page. Don't summarise it for me." (senior associate)
- "If it is wrong, I need to know how often it is wrong before I let a junior rely on it."
  (managing partner)
- "It cannot send client contracts to a public AI service." (IT lead)
- "Put the findings somewhere I can search across matters." (practice head)

## 5. Constraints surfaced

- Client data must stay within the firm's tenancy or a private deployment they control.
  A fully offline mode is a requirement for two specific clients.
- Nothing is final without a named lawyer approving it. The system proposes; a person
  disposes.
- Integration target is the practice-management system (built on HubSpot) and the firm's
  Slack. Not the document management system, at least in phase one.
- Budget and time: they want something usable on real matters in about eight weeks, with
  a measured error rate before rollout.

## 6. What we are not being asked to do

- Draft or redline contracts.
- Give legal advice or risk ratings that a lawyer has not reviewed.
- Replace the senior verification step. The goal is to make it faster and better aimed.

## 7. Recommendation

Build a clause-level reviewer that, for each of the 15 checklist items, either cites
the exact text with a page reference or says "not found", with a measured error rate on a
public benchmark before it touches a client contract. Route every output through a
review queue. Write findings back to the matter record so they are searchable.

Success in eight weeks looks like: the junior's 3.6 hours becomes roughly 1 hour of
reviewing proposed findings, the senior's check is aimed at the low-confidence items, and
the firm can quote a number for "how often does it miss a clause" because we measured it.

See [scope.md](scope.md) for what is in and out.
