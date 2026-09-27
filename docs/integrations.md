# Integrations: what happens when each one breaks

The rule: a downstream outage never blocks a lawyer from reviewing a contract. Reads
degrade to "unavailable, here is why". Writes go through a durable outbox and are
delivered later, exactly once.

## Failure-mode table

| System | Situation | What the lawyer sees | What the system does | Recovery |
|---|---|---|---|---|
| HubSpot | Down (5xx) or network timeout | Approve succeeds instantly. Findings page unchanged. | Outbox row stays `pending`; worker retries with exponential backoff (30s, 60s, 2m ... capped 1h) plus 20% jitter, up to 8 attempts | Automatic. `ccr-sync` or `crm_reconcile` |
| HubSpot | Rate limited (429, Retry-After) | Nothing | Waits exactly `Retry-After` seconds before the next attempt | Automatic |
| HubSpot | Rejects the request (4xx) | Nothing immediately; `/api/outbox` shows `failed: 1` | Row marked `failed` with the response body. No retry (it would fail the same way) | Human fixes the cause; reconciliation reopens failed rows older than a day, once |
| HubSpot | Note created but our process crashed before marking `sent` | Nothing | Next attempt searches for `[ccr:<key>]` in note bodies first and returns the existing id | Automatic, no duplicate |
| HubSpot | Deal not found by search moments after creation (eventual consistency) | Nothing | Create; on 409 duplicate, search again | Automatic |
| HubSpot | Token missing or revoked | `crm_lookup_matter` returns `status: unavailable, reason: not configured` | Writes still queue; nothing is lost | Add token, run `ccr-sync` |
| Slack | Webhook down | Nothing | Same outbox behaviour as HubSpot | Automatic |
| Slack | Webhook URL revoked (returns non-"ok") | Nothing | Row `failed` with Slack's body | Rotate URL, reconcile |
| Slack (inbound, future) | Forged or replayed request | Rejected with 401 | HMAC-SHA256 over `v0:ts:body`, constant-time compare, 5-minute window | n/a |
| Anthropic | Key missing | Engine falls back to `retrieval-hybrid`; scorecard shows which engine ran | `LLMReviewer` refuses to construct without a key | Add key |
| Anthropic | API error mid-review | That clause becomes `not found` with the error as the system note | Never fabricates; failure is in the safe direction | Re-run review |
| Everything | `CCR_OFFLINE=1` | Same UI, engine badge shows `retrieval-hybrid` | Every outbound HTTP call raises before connecting; outbox rows stay `pending` with the reason | Deliver later by running `ccr-sync` from a connected host against the same database |
| Database | Unreachable | Upload fails with 500 | Nothing partial: contract, review, findings, and outbox rows are one transaction | Restore connectivity |

## Idempotency

| Write | Key | Where the key lives remotely |
|---|---|---|
| Findings note on a matter | `hubspot:write_findings:<review id>` | In the note body as `[ccr:<key>]`, searchable |
| "Review created" message | `slack:review_created:<review id>` | Nowhere (Slack has no search on webhooks); dedupe is local only |
| "Review final" message | `slack:review_final:<review id>` | Same |
| Manual channel message from an agent | `slack:manual:<sha256(text)[:16]>` | Same; identical text within the outbox is sent once |

Local dedupe is a unique constraint on `integration_outbox.idempotency_key`. Remote
dedupe exists only where the remote system lets us search, which is why HubSpot notes
carry the key and Slack messages do not.

## Reconciliation

`ccr-sync` (and the `crm_reconcile` MCP tool) do three things, in order:

1. Drain due outbox rows.
2. For every review that is final, check an outbox row exists for its HubSpot write-back;
   enqueue if missing. Covers a crash between "decision saved" and "outbox row saved"
   (they are one transaction, so this should never fire; it is a belt for the braces).
3. Reopen `failed` rows older than one day, once, in case the cause was fixed.

Run it every 30 seconds in production (`docker-compose.yml` and the Helm chart do). It
is safe to run concurrently with the app and with itself.

## Access control on the MCP servers

Roles are declared per customer (`customers/<id>.yaml`, `access.roles`). In the pilot
the role is asserted by `CCR_MCP_ROLE` on the MCP client's environment, which is fine
for a single-tenant desktop deployment and not fine for anything shared. The Helm
chart's ingress notes describe the production path: terminate OIDC at the ingress and
map the identity's group claim to a role.

A denied call returns `status: denied` with the role and the file to edit; it does not
raise, so an agent can explain the situation instead of crashing.

## HubSpot specifics that cost time

Recorded in `src/reviewer/integrations/hubspot.py` so they stay next to the code:
eventually consistent search, note-to-deal association type id 214, `hs_timestamp` as an
epoch-millisecond string, 100 requests per 10 seconds, no server-side idempotency.

## Not yet wired

- Inbound Slack interactions (approve from Slack). Signature verification exists and is
  tested; the endpoint is not.
- OIDC on the web app. The pilot runs inside the firm's network with no login; the
  ingress-level OIDC pattern is described in the Helm values.
- Salesforce adapter. The CRM layer is a protocol with one implementation (HubSpot).
  Adding Salesforce is a second module with the same three methods.
