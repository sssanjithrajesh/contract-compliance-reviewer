"""MCP servers, called in-process through the real MCP tool dispatch."""

import asyncio
import json

import httpx
import pytest

from reviewer.app import db
from reviewer.config import load_customer
from reviewer.mcp import crm, documents, notify
from tests.test_integrations import FakeHubSpot
from tests.test_pipeline import CONTRACT


def call(server, tool, **args):
    result = asyncio.run(server.call_tool(tool, args))
    # Prefer structured content; fall back to the text block.
    if getattr(result, "structured_content", None) is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setenv("CCR_REVIEWER", "keyword")
    monkeypatch.setenv("CCR_MCP_ROLE", "partner")
    from reviewer.integrations import outbox as _  # noqa: F401

    return db.make_session_factory(f"sqlite:///{tmp_path / 'mcp.db'}")


def cfg():
    return load_customer("harlow-pryce")


def test_documents_server_lists_tools_and_full_flow(factory):
    server = documents.build(factory, cfg)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {
        "list_contracts",
        "get_review",
        "review_contract",
        "search_contract",
        "decide_finding",
    } <= names

    out = call(server, "review_contract", filename="msa.txt", text=CONTRACT)
    assert out["status"] == "ok" and out["summary"]["total"] == 15
    cid = out["contract_id"]

    passages = call(server, "search_contract", contract_id=cid, query="governed by the laws")
    assert any("New York" in p["text"] for p in passages["passages"])

    listed = call(server, "list_contracts")["contracts"]
    assert listed[0]["contract_id"] == cid and listed[0]["review"]["proposed"] == 15

    review = call(server, "get_review", contract_id=cid)
    gov = next(f for f in review["findings"] if f["clause_type"] == "governing_law")
    assert gov["present"] and gov["status"] == "proposed"


def test_documents_server_enforces_roles(factory, monkeypatch):
    server = documents.build(factory, cfg)
    monkeypatch.setenv("CCR_MCP_ROLE", "associate")
    out = call(server, "decide_finding", finding_id=1, status="approved", who="X")
    assert out["status"] == "denied" and out["role"] == "associate"
    monkeypatch.setenv("CCR_MCP_ROLE", "nobody")
    assert call(server, "list_contracts")["status"] == "denied"


def test_crm_server_degrades_gracefully_and_queues(factory, monkeypatch):
    # No token: lookup reports "not configured" rather than raising.
    monkeypatch.delenv("HUBSPOT_PRIVATE_APP_TOKEN", raising=False)
    server = crm.build(factory, cfg)
    out = call(server, "crm_lookup_matter", name="Anything")
    assert out["status"] == "unavailable" and out["reason"] == "not configured"

    # With a token but HubSpot returning 503 forever: unavailable, retry=True.
    monkeypatch.setenv("HUBSPOT_PRIVATE_APP_TOKEN", "t")
    down = crm.build(factory, cfg, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    # patch sleep so the retry loop does not actually wait
    monkeypatch.setattr("reviewer.integrations.http.time.sleep", lambda s: None)
    out = call(down, "crm_lookup_matter", name="Anything")
    assert out["status"] == "unavailable" and out["retry"] is True

    # Offline mode: refused before any network call.
    monkeypatch.setenv("CCR_OFFLINE", "1")
    out = call(down, "crm_lookup_matter", name="Anything")
    assert out["status"] == "unavailable" and out["reason"] == "offline mode"
    monkeypatch.delenv("CCR_OFFLINE")

    # Happy path with the fake: write-back queues, reconcile delivers.
    fake = FakeHubSpot()
    ok = crm.build(factory, cfg, transport=httpx.MockTransport(fake.handler))
    docs = documents.build(factory, cfg)
    created = call(docs, "review_contract", filename="msa.txt", text=CONTRACT)
    cid = created["contract_id"]
    review = call(docs, "get_review", contract_id=cid)
    with factory() as s:
        for f in s.query(db.Finding).all():
            call(docs, "decide_finding", finding_id=f.id, status="approved", who="A. Harlow")
    queued = call(ok, "crm_write_findings", contract_id=cid)
    assert queued["status"] == "queued" and queued["review_final"] is True
    monkeypatch.setenv("CCR_MCP_ROLE", "integration")
    result = call(ok, "crm_reconcile")
    assert result["drained"]["sent"] >= 1 and len(fake.notes) == 1
    assert review["contract"] == "msa.txt"


def test_notify_server_queues_and_dedupes(factory):
    server = notify.build(factory, cfg)
    assert call(server, "notify_channel", text="hello team")["status"] == "queued"
    assert call(server, "notify_channel", text="hello team")["status"] == "duplicate"
