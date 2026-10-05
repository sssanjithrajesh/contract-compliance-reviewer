"""HubSpot CRM adapter: matters are Deals, findings are Notes on the deal.

HubSpot quirks this code works around (each one cost time; documented so the next
person does not rediscover them):

1. Search is eventually consistent. A deal created a moment ago may not be found by
   /crm/v3/objects/deals/search for several seconds. So: search, and if not found, create,
   and if create reports a duplicate, search again. Never assume "not found" is final.
2. Notes are engagements. Creating one is two calls: create the note, then associate it
   with the deal (or use the `associations` body on create, which is what we do, but the
   association type id for note->deal is 214 and is not discoverable from the UI).
3. Timestamps on notes (hs_timestamp) are required and must be epoch milliseconds as a
   string, not ISO 8601, despite what the property type says.
4. Rate limit is 100 requests per 10 seconds per private app, returned as HTTP 429 with a
   Retry-After header in seconds. The http client honours it.
5. There is no server-side idempotency. We embed the idempotency key in the note body
   (`[ccr:<key>]`) and search for it before creating, so retries and reconciliation are safe.
"""

from __future__ import annotations

import time

import httpx

from reviewer.integrations.http import Client, PermanentError

BASE = "https://api.hubapi.com"
NOTE_TO_DEAL_ASSOCIATION = 214


class HubSpot:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.client = Client(
            BASE,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            transport=transport,
            sleep=sleep,
        )

    # -- matters (deals) ------------------------------------------------------------

    def find_deal(self, name: str) -> dict | None:
        body = {
            "filterGroups": [{"filters": [{"propertyName": "dealname", "operator": "EQ", "value": name}]}],
            "properties": ["dealname", "dealstage", "pipeline"],
            "limit": 1,
        }
        r = self.client.post("/crm/v3/objects/deals/search", json=body)
        results = r.json().get("results", [])
        return results[0] if results else None

    def ensure_deal(self, name: str) -> dict:
        found = self.find_deal(name)
        if found:
            return found
        try:
            r = self.client.post("/crm/v3/objects/deals", json={"properties": {"dealname": name}})
            return r.json()
        except PermanentError as exc:
            if "409" in str(exc):  # created concurrently; search is eventually consistent
                found = self.find_deal(name)
                if found:
                    return found
            raise

    # -- findings (notes) -----------------------------------------------------------

    def find_note_by_key(self, key: str) -> dict | None:
        body = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "hs_note_body",
                            "operator": "CONTAINS_TOKEN",
                            "value": f"ccr:{key}",
                        }
                    ]
                }
            ],
            "properties": ["hs_note_body"],
            "limit": 1,
        }
        r = self.client.post("/crm/v3/objects/notes/search", json=body)
        results = r.json().get("results", [])
        return results[0] if results else None

    def write_findings_note(self, key: str, deal_id: str, body_text: str) -> str:
        existing = self.find_note_by_key(key)
        if existing:
            return existing["id"]
        payload = {
            "properties": {
                "hs_note_body": f"{body_text}\n\n[ccr:{key}]",
                "hs_timestamp": str(int(time.time() * 1000)),
            },
            "associations": [
                {
                    "to": {"id": deal_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": NOTE_TO_DEAL_ASSOCIATION,
                        }
                    ],
                }
            ],
        }
        r = self.client.post("/crm/v3/objects/notes", json=payload)
        return r.json()["id"]


def render_findings(review: dict) -> str:
    """Plain-text note body from an exported review (service.export_review)."""
    lines = [f"Contract review: {review['contract']} (engine {review['reviewer']})", ""]
    for f in review["findings"]:
        if f["status"] != "approved":
            continue
        status = "FOUND" if f["present"] else "not found"
        lines.append(f"- {f['clause_type']}: {status}")
        for c in f["citations"][:2]:
            snippet = c["text"].strip().replace("\n", " ")
            lines.append(f"    p.{c['page']}: {snippet[:180]}{'...' if len(snippet) > 180 else ''}")
        lines.append(f"    approved by {f['decided_by']} at {f['decided_at']}")
    s = review["summary"]
    lines += ["", f"{s['approved']} approved, {s['rejected']} rejected, {s['proposed']} awaiting."]
    return "\n".join(lines)


def make_dispatcher(hubspot: HubSpot):
    """Outbox dispatcher: (kind, key, payload) -> remote id."""

    def dispatch(kind: str, key: str, payload: dict) -> str:
        if kind != "write_findings":
            raise PermanentError(f"hubspot dispatcher does not handle kind {kind!r}")
        deal = hubspot.ensure_deal(payload["matter_name"])
        return hubspot.write_findings_note(key, deal["id"], render_findings(payload["review"]))

    return dispatch
