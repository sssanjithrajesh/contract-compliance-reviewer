# ADR-0003: Integrations via a durable outbox; MCP servers split by trust boundary

**Status:** Accepted
**Date:** 2026-09-27
**Deciders:** forward-deployed engineer

## Context

Phase 3 connects the reviewer to the firm's CRM (HubSpot) and Slack, and exposes it to
agents over MCP. Discovery gave two constraints: a lawyer's Approve must never fail
because a third-party API is slow, and the firm's IT lead wants to grant an agent read
access to reviews without granting it the ability to write to the CRM.

## Options considered

### Option A: Call HubSpot and Slack synchronously from the request handler

Simplest. Rejected: HubSpot's 100 requests per 10 seconds and its 5xx rate under load
mean Approve would intermittently fail or hang. Retrying inline makes the UI slower
exactly when the integration is unhealthy. And a crash after the remote call but before
the local commit duplicates notes on retry.

### Option B: Background thread or task queue (Celery, RQ) with at-least-once delivery

Standard. Rejected for the pilot: a broker is another component for a two-person IT
team to run, and at-least-once without idempotency still duplicates. The idempotency
work is needed regardless, so the broker adds cost without removing the hard part.

### Option C: Transactional outbox table in the application database, drained by a worker

The outbox row is written in the same transaction as the user's decision. A worker
(`ccr-sync`) drains it with backoff and jitter, honouring Retry-After. Each row has an
idempotency key; HubSpot notes carry the key in their body so a retry can find a note
created by a crashed attempt. Reconciliation closes the remaining gaps.

### Option D: One MCP server exposing every tool, with access control inside each tool

Fewer processes. Rejected: MCP clients are granted a server, not a tool. If the firm
wants an agent to read reviews but never touch the CRM, the only reliable control is to
not give that agent the CRM server at all. Per-tool role checks are still applied inside
each server as a second layer.

## Decision

Option C for delivery, and three MCP servers (documents, crm, notify) instead of Option
D. Roles per tool are declared in the customer YAML and enforced by a decorator that
also converts integration failures into structured `status` results, so an agent can
explain a problem rather than crash on it.

## Consequences

- Easier: Approve is instant and never fails for integration reasons. Offline mode falls
  out naturally: rows queue, and a connected host drains them later.
- Easier: the failure-mode table in `docs/integrations.md` is short because every write
  has one path.
- Harder: eventual delivery. A partner who approves the last finding and immediately
  opens HubSpot may not see the note for up to 30 seconds. Acceptable; noted in the
  runbook.
- Harder: Slack has no remote dedupe, so a crash between send and mark-sent can
  double-post a notification. Tolerable for notifications; would not be for CRM writes,
  which is why those carry a searchable key.
- Debt: role assertion via `CCR_MCP_ROLE` is a pilot shortcut. Production needs identity
  from the transport (OIDC), tracked in the Helm values and integrations doc.

## Cost

Roughly eight hours: HTTP client with retry semantics, outbox and worker, HubSpot and
Slack adapters with fakes, three MCP servers, tests for all of it. No infrastructure
added beyond the existing database.

## Revisit when

- Outbox depth regularly exceeds a few hundred rows or delivery latency matters at
  the seconds level. Then a broker earns its keep.
- A second CRM adapter (Salesforce) is added. If the two share most of their code, the
  adapter protocol is right; if not, redesign it before the third.
- The firm moves to a shared deployment. Role assertion must move to OIDC first.
