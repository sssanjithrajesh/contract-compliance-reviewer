"""Salesforce CRM adapter: matters are Opportunities, findings are Tasks.

Same three methods as HubSpot (lookup, write-back, reconcile via the outbox). The CRM
layer is a protocol; this is the second implementation the Glean/Anthropic interview
asks you to design.

Salesforce quirks this code works around:

1. Names are not unique. Two Opportunities can share a Name. We take the first match
   and record the Id; we never key write-back on the name alone.
2. SOQL strings escape a single quote by doubling it. Unescaped input is an injection.
3. There is no server-side idempotency on Task create. We stamp `[ccr:<key>]` in
   Description and query for it before insert, same pattern as HubSpot notes.
4. Task.WhatId links to the Opportunity. WhoId is a person; we leave it empty.
5. API version is pinned (v59.0) so a seasonal upgrade cannot silently change fields.
"""

from __future__ import annotations

import httpx

from reviewer.integrations.http import Client, PermanentError
from reviewer.integrations.hubspot import render_findings

API = "/services/data/v59.0"


def _soql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


class Salesforce:
    def __init__(
        self,
        token: str,
        instance_url: str,
        transport: httpx.BaseTransport | None = None,
    ):
        self.client = Client(
            instance_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            transport=transport,
        )

    def find_opportunity(self, name: str) -> dict | None:
        q = f"SELECT Id, Name, StageName FROM Opportunity WHERE Name = '{_soql_escape(name)}' LIMIT 1"
        r = self.client.get(f"{API}/query", params={"q": q})
        records = r.json().get("records", [])
        return records[0] if records else None

    def ensure_opportunity(self, name: str) -> dict:
        found = self.find_opportunity(name)
        if found:
            return found
        try:
            r = self.client.post(f"{API}/sobjects/Opportunity", json={"Name": name, "StageName": "Prospecting", "CloseDate": "2099-12-31"})
            data = r.json()
            return {"Id": data["id"], "Name": name}
        except PermanentError as exc:
            if "DUPLICATE" in str(exc).upper() or "409" in str(exc):
                found = self.find_opportunity(name)
                if found:
                    return found
            raise

    def find_task_by_key(self, key: str) -> dict | None:
        token = _soql_escape(f"ccr:{key}")
        q = f"SELECT Id, Description FROM Task WHERE Description LIKE '%{token}%' LIMIT 1"
        r = self.client.get(f"{API}/query", params={"q": q})
        records = r.json().get("records", [])
        return records[0] if records else None

    def write_findings_task(self, key: str, opportunity_id: str, body_text: str) -> str:
        existing = self.find_task_by_key(key)
        if existing:
            return existing["Id"]
        r = self.client.post(
            f"{API}/sobjects/Task",
            json={
                "Subject": "Contract review findings",
                "WhatId": opportunity_id,
                "Status": "Completed",
                "Description": f"{body_text}\n\n[ccr:{key}]",
            },
        )
        return r.json()["id"]


def make_dispatcher(salesforce: Salesforce):
    def dispatch(kind: str, key: str, payload: dict) -> str:
        if kind != "write_findings":
            raise PermanentError(f"salesforce dispatcher does not handle kind {kind!r}")
        opp = salesforce.ensure_opportunity(payload["matter_name"])
        oid = opp.get("Id") or opp.get("id")
        return salesforce.write_findings_task(key, oid, render_findings(payload["review"]))

    return dispatch

