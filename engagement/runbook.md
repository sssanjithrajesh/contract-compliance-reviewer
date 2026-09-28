# Runbook: Contract Compliance Reviewer

For whoever is on call for the deployment. Written so a partner's assistant at the firm
could follow the first section and an engineer could follow the rest.

## 0. What is running

| Component | Process | Health check | Owner |
|---|---|---|---|
| Review app | `ccr-serve` (uvicorn, port 8000) | `GET /healthz` returns `{"ok": true}` | Vendor (us) |
| Sync worker | `ccr-sync --loop` | `GET /api/outbox` shows `pending` not growing | Vendor |
| Database | Postgres (prod) or SQLite (pilot) | `psql -c 'select 1'` | Customer IT |
| SSO proxy | oauth2-proxy / Cloudflare Access | Login page appears when logged out | Customer IT |
| HubSpot | Customer's portal | Notes appear on the deal within 2 minutes of approval | Customer |
| Slack | `#contract-review` webhook | Message appears when a review is created | Customer |

The app never calls an LLM unless `CCR_REVIEWER=llm` and a key is set. In `offline: true`
customers (Meridian) every outbound HTTP call is blocked at the client and raises
`OfflineError`; that is expected, not a fault.

## 1. Symptoms a non-engineer can triage

| What you see | Most likely cause | Do this |
|---|---|---|
| Upload returns "could not extract text" (422) | Scanned PDF with no text layer | Ask for the original file or a text export. OCR is not enabled. |
| Every clause says "not found" on a contract you know is complete | Contract is very short, or the wrong customer config is loaded | Check the header on the review page shows the right firm name. If short, this is a known threshold limit (see ADR-0002). |
| "A named reviewer is required" when approving | The name field was blank (pilot) or you are not logged in through SSO (production) | Type your name / log in again. |
| "No authenticated user" (401) when approving | SSO proxy is not passing the identity header | Escalate to customer IT (section 3.4). |
| Approved a finding, nothing in HubSpot after 10 min | Sync worker stopped or HubSpot token expired | Section 3.2. |
| Slack messages stopped | Webhook revoked or channel archived | Section 3.3. |

## 2. Daily checks (2 minutes)

```
curl -s https://<host>/healthz
curl -s https://<host>/api/outbox      # pending should be small and not the same items as yesterday
```

If `pending` contains items with `attempts >= 5`, something upstream has been failing for
hours. Look at the `last_error` on those items before touching anything.

## 3. Incidents

### 3.1 App is down

1. `kubectl -n ccr get pods` (or `docker compose ps`). A CrashLoop on `app` is almost
   always a bad `DATABASE_URL` or a missing customer YAML; read the first 30 lines of logs.
2. Roll back: `helm rollback ccr` or `docker compose up -d app@<previous tag>`. The
   database schema is additive, so rollback is safe.
3. Nothing is lost. Uploads that did not complete were never stored.

### 3.2 HubSpot write-back not arriving

1. `GET /api/outbox`. If items are pending with `last_error` mentioning 401 or 403, the
   private-app token was rotated: update the secret and restart `ccr-sync`.
2. If `last_error` is 429, we are being rate-limited. The worker already honours
   `Retry-After`; do nothing, it will drain.
3. If items show `attempts = 8` (dead), run `ccr-sync --reconcile` after fixing the cause.
   It re-queues dead items whose finding is still approved. Idempotency keys mean a
   double-send writes the same note once.
4. Never edit the outbox table by hand. Every write-back is derived from the review, so
   the recovery path is always "fix cause, reconcile".

### 3.3 Slack notifications stopped

1. `POST` a test message with the webhook URL from the secret. A 404 means the webhook
   was deleted in Slack; ask the customer's Slack admin for a new one.
2. If the customer sets up slash-command callbacks, signatures are verified with
   `SLACK_SIGNING_SECRET`; a 401 on the callback means that secret rotated.

### 3.4 Identity / SSO

In production `CCR_IDENTITY_MODE=proxy_header`. The app trusts the header **only** because
the proxy strips client-supplied copies of it. Verify that before anything else:

```
curl -s -H "X-Forwarded-User: attacker" https://<host>/healthz -o /dev/null -w "%{http_code}"
```

should be redirected to the login page, not 200. If it is 200, the proxy is misconfigured
and approvals are not trustworthy until it is fixed. Set `CCR_IDENTITY_MODE=form` only in a
pilot with no external exposure.

### 3.5 Eval regression gate failed in CI

Somebody's change made the reviewer worse on the committed eval set. Do not bump the gate
to make the build green. Read the per-clause table in the CI log; the clause that dropped
tells you what the change broke. If the change is a deliberate trade (e.g. fewer
hallucinations at the cost of recall), say so in the PR and update the gate in the same
PR with `ccr-eval --update-gate` so the reviewer can see both numbers move.

## 4. Onboarding a new customer

1. Copy `customers/harlow-pryce.yaml` to `customers/<id>.yaml`; edit clauses, integrations,
   roles, identity mode.
2. If the domain needs clause types not in `src/reviewer/clauses.py`, add them there with
   keywords and a "why it matters" sentence. This is the only code change.
3. Write at least two sample contracts (one complete, one deficient) into
   `evals/contracts/` and annotate anchors in a `scripts/build_<domain>_evals.py`.
4. `uv run ccr-eval --customer <id>`; commit the generated `docs/scorecard-<id>.svg`.
5. Deploy with `CCR_CUSTOMER=<id>`.

Meridian Health took one afternoon by this list; see ADR-0004 for what we learned.

## 5. Secrets and rotation

| Secret | Used by | Rotate by |
|---|---|---|
| `HUBSPOT_PRIVATE_APP_TOKEN` | ccr-sync | Regenerate in HubSpot, update k8s secret, restart sync |
| `SLACK_WEBHOOK_URL` | ccr-sync | New webhook in Slack app, update secret, restart sync |
| `SLACK_SIGNING_SECRET` | app (callbacks) | Regenerate in Slack app, update secret, restart app |
| `ANTHROPIC_API_KEY` | app (only if `CCR_REVIEWER=llm`) | Rotate in console, update secret, restart app |
| `DATABASE_URL` | app, sync | Customer IT; schedule a restart |

No secret is read from a file inside the image. The Helm chart mounts them from a
`Secret` named `ccr-secrets`.

## 6. Contacts

Vendor on-call: the engagement lead (see `engagement/scope.md`). Customer side: the
practice-group partner sponsoring the pilot and one IT contact for SSO and Postgres.
