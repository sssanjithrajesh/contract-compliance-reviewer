---
name: contract-review
description: Review a contract against a customer's clause checklist with page-cited findings, refuse when evidence is missing, route every finding through a named human approver, and write approved results back to the matter record. Use when asked to review, check, or summarise a contract, or to find a specific clause type in one.
---

# Contract review

This skill wraps the Contract Compliance Reviewer. It is customer-agnostic: the clause
list, integrations, and access rules come from `customers/<id>.yaml`, selected with
`CCR_CUSTOMER`. Adding a customer means adding a YAML file, not touching this skill.

## When to use

- "Review this contract" / "what does this agreement say about X"
- "Does this contract have a non-compete / liability cap / auto-renewal"
- "Summarise the risks in this contract for the partner"
- "Write the approved findings to the matter"

## Hard rules

1. Every claim that a clause exists must carry a citation (page and character range)
   produced by the `review_contract` or `search_contract` tool. Never quote from memory.
2. If the tool returns `present: false`, say "not found". Do not speculate about what
   the contract "probably" says.
3. Findings with `status: proposed` are not final. Say so whenever you report them.
4. Never call `decide_finding` on a user's behalf unless they have named themselves and
   asked you to record a decision. The name goes in `who`.
5. If a CRM or notification tool returns `status: unavailable`, tell the user the action
   is queued or blocked and why. Do not retry in a loop; the outbox handles retries.

## Tools (MCP servers)

| Server | Tool | Role needed | Use |
|---|---|---|---|
| ccr-documents | `list_clause_types` | associate | What this customer checks |
| ccr-documents | `review_contract(filename, text)` | associate | Run the full checklist |
| ccr-documents | `search_contract(contract_id, query)` | associate | Find a passage the checklist did not cover |
| ccr-documents | `get_review(contract_id)` | associate | Current findings and decisions |
| ccr-documents | `list_contracts()` | associate | Queue overview |
| ccr-documents | `decide_finding(finding_id, status, who, note)` | partner | Record a named decision |
| ccr-crm | `crm_lookup_matter(name)` | partner | Confirm the matter exists |
| ccr-crm | `crm_write_findings(contract_id)` | partner | Queue write-back (only works when the review is final) |
| ccr-crm | `crm_reconcile()` | integration | Drain the outbox, repair gaps |
| ccr-notify | `notify_channel(text)` | partner | Tell the team |

## Procedure

1. `list_clause_types` to learn the checklist for this customer.
2. `review_contract` with the document text. Report: N found, M not found, all proposed.
3. For each high-attention item (see `prompts/risk-triage.md`), quote the citation and
   the plain-English "why it matters" from the tool output.
4. If the user asks about something not on the checklist, `search_contract` and present
   the passages as passages, not as findings.
5. When the user (named) approves or rejects, call `decide_finding` per item.
6. When `get_review` shows `summary.final: true`, offer `crm_write_findings`; report the
   `status` it returns verbatim (`queued`, `already_queued_or_not_final`, `unavailable`).

## Eval hooks

Any change to prompts, thresholds, or the clause list must keep the regression gate green:

```bash
uv run ccr-eval --gate        # production engine against 120 CUAD cases
uv run pytest                 # includes MCP tool tests and integration fakes
```

If you change `prompts/*.md`, add at least one case to `evals/cases/` that would have
caught the failure you were fixing, then update `evals/gate.json` with `--update-gate`
only if every metric moved in the right direction. Record the change in an ADR.

## Files

- `prompts/extraction.md` - the grounded-quote extraction prompt used by the LLM reviewer
- `prompts/risk-triage.md` - how findings are ranked for the partner summary
- `../../customers/*.yaml` - per-customer configuration this skill reads
