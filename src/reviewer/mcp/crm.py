"""MCP server: the firm's CRM (HubSpot or Salesforce) as matter records.

    uv run ccr-mcp-crm

Writes never go straight to HubSpot from a tool call; they are enqueued in the outbox and
delivered by ccr-sync. So `crm_write_findings` returns immediately with "queued" even if
HubSpot is down, and `crm_reconcile` reports what the outbox knows.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from reviewer.app import db
from reviewer.config import Secrets, current_customer
from reviewer.integrations import hubspot as hs
from reviewer.integrations import outbox, salesforce as sf, sync
from reviewer.mcp.common import guarded


def build(session_factory=None, cfg_getter=current_customer, transport=None) -> MCPServer:
    session_factory = session_factory or db.make_session_factory()
    server = MCPServer(
        "ccr-crm",
        instructions="Matter records for contract reviews. Writes are queued and idempotent.",
    )

    def _lookup(name: str) -> dict:
        provider = cfg_getter().integrations.crm.provider
        if provider == "salesforce":
            token = Secrets.get(Secrets.SALESFORCE_TOKEN, required=False)
            instance = Secrets.get(Secrets.SALESFORCE_INSTANCE, required=False)
            if not token or not instance:
                return {"status": "unavailable", "reason": "not configured"}
            rec = sf.Salesforce(token, instance, transport=transport).find_opportunity(name)
            if rec is None:
                return {"status": "not_found", "name": name}
            return {"status": "ok", "matter_id": rec.get("Id"), "properties": rec}
        token = Secrets.get(Secrets.HUBSPOT_TOKEN, required=False)
        if not token:
            return {"status": "unavailable", "reason": "not configured"}
        deal = hs.HubSpot(token, transport=transport).find_deal(name)
        if deal is None:
            return {"status": "not_found", "name": name}
        return {"status": "ok", "matter_id": deal["id"], "properties": deal.get("properties", {})}

    @server.tool(description="Look up a matter (HubSpot deal or Salesforce Opportunity) by name. Read-only.")
    @guarded("crm_lookup_matter", cfg_getter)
    def crm_lookup_matter(name: str) -> dict:
        return _lookup(name)

    @server.tool(
        description="Queue the approved findings of a contract's final review for write-back to its matter record."
    )
    @guarded("crm_write_findings", cfg_getter)
    def crm_write_findings(contract_id: int) -> dict:
        cfg = cfg_getter()
        with session_factory() as s:
            c = s.get(db.Contract, contract_id)
            if c is None or not c.reviews:
                return {"status": "not_found", "contract_id": contract_id}
            review = c.reviews[-1]
            before = outbox.pending_summary(s)
            sync.enqueue_review_final(s, cfg, review, "http://localhost:8000")
            s.commit()
            after = outbox.pending_summary(s)
            queued = after.get("pending", 0) > before.get("pending", 0)
            return {
                "status": "queued" if queued else "already_queued_or_not_final",
                "contract_id": contract_id,
                "review_final": sync.service.review_summary(review)["final"],
                "outbox": after,
            }

    @server.tool(
        description="Drain the outbox once and re-enqueue any final review missing a write-back. Integration role."
    )
    @guarded("crm_reconcile", cfg_getter)
    def crm_reconcile() -> dict:
        cfg = cfg_getter()
        with session_factory() as s:
            dispatchers = sync.build_dispatchers(cfg, transport=transport)
            drained = outbox.process_once(s, dispatchers)
            fixed = sync.reconcile(s, cfg)
            return {
                "status": "ok",
                "drained": drained,
                "reconciled": fixed,
                "outbox": outbox.pending_summary(s),
            }

    return server


def main() -> None:
    build().run(transport="stdio")
