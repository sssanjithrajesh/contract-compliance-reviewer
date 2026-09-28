"""Integration layer tests. No network: every HTTP call hits an in-memory fake transport."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from reviewer.app import db, service
from reviewer.config import load_customer
from reviewer.integrations import hubspot as hs
from reviewer.integrations import outbox, slack, sync
from reviewer.integrations.http import (
    Client,
    OfflineError,
    PermanentError,
    RetryableError,
    RetryPolicy,
)
from tests.test_pipeline import CONTRACT

# --- http client -----------------------------------------------------------------------


def make_client(handler, attempts=4):
    sleeps: list[float] = []
    client = Client(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        policy=RetryPolicy(attempts=attempts, base_seconds=0.1, jitter=0.0),
        sleep=sleeps.append,
    )
    return client, sleeps


def test_retries_on_503_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})

    client, sleeps = make_client(handler)
    assert client.get("/x").json() == {"ok": True}
    assert calls["n"] == 3 and sleeps == [0.1, 0.2]  # exponential, jitter disabled


def test_honours_retry_after_on_429():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, text="ok")

    client, sleeps = make_client(handler)
    client.get("/x")
    assert sleeps == [7.0]


def test_gives_up_after_attempts_with_retryable_error():
    client, sleeps = make_client(lambda r: httpx.Response(500), attempts=3)
    with pytest.raises(RetryableError):
        client.get("/x")
    assert len(sleeps) == 2


def test_4xx_is_permanent_and_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad")

    client, _ = make_client(handler)
    with pytest.raises(PermanentError):
        client.post("/x", json={})
    assert calls["n"] == 1


def test_offline_flag_blocks_all_outbound(monkeypatch):
    monkeypatch.setenv("CCR_OFFLINE", "1")
    client, _ = make_client(lambda r: httpx.Response(200))
    with pytest.raises(OfflineError):
        client.get("/x")


# --- hubspot ----------------------------------------------------------------------------


class FakeHubSpot:
    """Enough of HubSpot's CRM v3 to exercise search-then-create and note idempotency."""

    def __init__(self, flaky_first_create=False):
        self.deals: dict[str, dict] = {}
        self.notes: list[dict] = []
        self.calls: list[str] = []
        self.flaky_first_create = flaky_first_create

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        body = json.loads(request.content or b"{}")
        if path == "/crm/v3/objects/deals/search":
            name = body["filterGroups"][0]["filters"][0]["value"]
            hit = [d for d in self.deals.values() if d["properties"]["dealname"] == name]
            return httpx.Response(200, json={"results": hit})
        if path == "/crm/v3/objects/deals":
            if self.flaky_first_create:
                self.flaky_first_create = False
                return httpx.Response(503)
            deal = {"id": str(100 + len(self.deals)), "properties": body["properties"]}
            self.deals[deal["id"]] = deal
            return httpx.Response(201, json=deal)
        if path == "/crm/v3/objects/notes/search":
            token = body["filterGroups"][0]["filters"][0]["value"]
            hit = [n for n in self.notes if token in n["properties"]["hs_note_body"]]
            return httpx.Response(200, json={"results": hit})
        if path == "/crm/v3/objects/notes":
            assert body["properties"]["hs_timestamp"].isdigit(), "hs_timestamp must be epoch ms string"
            assert body["associations"][0]["types"][0]["associationTypeId"] == 214
            note = {"id": str(900 + len(self.notes)), "properties": body["properties"]}
            self.notes.append(note)
            return httpx.Response(201, json=note)
        return httpx.Response(404)


def test_hubspot_ensure_deal_creates_then_finds_and_note_is_idempotent():
    fake = FakeHubSpot(flaky_first_create=True)
    h = hs.HubSpot("token", transport=httpx.MockTransport(fake.handler), sleep=lambda s: None)
    deal = h.ensure_deal("Paxmedica Master Service Agreement")
    assert deal["id"] == "100"
    assert h.ensure_deal("Paxmedica Master Service Agreement")["id"] == "100"  # found, not duplicated
    n1 = h.write_findings_note("k1", deal["id"], "body")
    n2 = h.write_findings_note("k1", deal["id"], "body")
    assert n1 == n2 and len(fake.notes) == 1
    assert "[ccr:k1]" in fake.notes[0]["properties"]["hs_note_body"]


# --- slack ------------------------------------------------------------------------------


def test_slack_notify_and_signature_verification():
    seen = {}

    def handler(request):
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    s = slack.Slack("https://hooks.slack.com/services/T/B/X", transport=httpx.MockTransport(handler))
    assert s.notify("hello", [{"type": "section"}]) == "ok"
    assert seen["payload"]["text"] == "hello"

    secret, ts, body = "shh", str(int(time.time())), b"payload=1"
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    assert slack.verify_signature(secret, ts, body, sig)
    tampered = sig[:-1] + ("1" if sig[-1] == "0" else "0")  # always differs from the real last char
    assert not slack.verify_signature(secret, ts, body, tampered)
    assert not slack.verify_signature(secret, str(int(time.time()) - 600), body, sig)  # replay


# --- outbox -----------------------------------------------------------------------------


@pytest.fixture
def session(tmp_path):
    from reviewer.integrations import outbox as _  # noqa: F401  register table

    factory = db.make_session_factory(f"sqlite:///{tmp_path / 'o.db'}")
    with factory() as s:
        yield s


def test_outbox_enqueue_is_idempotent_and_processes_with_backoff(session):
    assert outbox.enqueue(session, "slack", "notify", "k", {"text": "a"}) is not None
    assert outbox.enqueue(session, "slack", "notify", "k", {"text": "a"}) is None
    session.commit()

    attempts = {"n": 0}

    def flaky(kind, key, payload):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RetryableError("503", retry_after=60)
        return "remote-1"

    now = datetime.now(UTC)
    counts = outbox.process_once(session, {"slack": flaky}, now=now)
    assert counts["retried"] == 1
    item = session.query(outbox.OutboxItem).one()
    assert item.status == "pending" and item.attempts == 1
    # not due yet
    assert outbox.process_once(session, {"slack": flaky}, now=now + timedelta(seconds=5))["sent"] == 0
    # due
    assert outbox.process_once(session, {"slack": flaky}, now=now + timedelta(seconds=120))["sent"] == 1
    assert session.query(outbox.OutboxItem).one().remote_id == "remote-1"


def test_outbox_permanent_error_fails_fast_and_offline_keeps_pending(session, monkeypatch):
    outbox.enqueue(session, "hubspot", "write_findings", "k1", {})
    outbox.enqueue(session, "hubspot", "write_findings", "k2", {})
    session.commit()

    def bad(kind, key, payload):
        if key == "k1":
            raise PermanentError("400")
        raise OfflineError("offline")

    counts = outbox.process_once(session, {"hubspot": bad})
    assert counts["failed"] == 1 and counts["skipped"] == 1
    statuses = {i.idempotency_key: i.status for i in session.query(outbox.OutboxItem)}
    assert statuses == {"k1": "failed", "k2": "pending"}


# --- end to end: decisions enqueue write-back, reconciliation fills gaps -----------------


def test_review_final_enqueues_hubspot_and_slack_and_reconcile_is_idempotent(session):
    cfg = load_customer("harlow-pryce")
    contract = service.store_contract(session, CONTRACT.encode(), "msa.txt")
    review = service.run_review(session, contract, "keyword", cfg.clauses)
    sync.enqueue_review_created(session, cfg, review, "http://t")
    session.commit()
    assert {i.kind for i in session.query(outbox.OutboxItem)} == {"notify"}

    for f in review.findings:
        service.decide(session, f.id, "approved", "A. Harlow")
    sync.enqueue_review_final(session, cfg, review, "http://t")
    session.commit()
    keys = sorted(i.idempotency_key for i in session.query(outbox.OutboxItem))
    assert keys == [
        f"hubspot:write_findings:{review.id}",
        f"slack:review_created:{review.id}",
        f"slack:review_final:{review.id}",
    ]

    # Deliver through the fake HubSpot and a fake Slack; then reconcile adds nothing.
    fake = FakeHubSpot()
    dispatchers = {
        "hubspot": hs.make_dispatcher(hs.HubSpot("t", transport=httpx.MockTransport(fake.handler))),
        "slack": lambda kind, key, payload: "ok",
    }
    counts = outbox.process_once(session, dispatchers)
    assert counts["sent"] == 3 and len(fake.notes) == 1
    assert "governing_law: FOUND" in fake.notes[0]["properties"]["hs_note_body"]
    assert sync.reconcile(session, cfg) == {"enqueued_missing": 0, "reopened_failed": 0}

    # Simulate a lost row: reconciliation re-creates it, and HubSpot's key search dedupes.
    session.query(outbox.OutboxItem).filter_by(kind="write_findings").delete()
    session.commit()
    assert sync.reconcile(session, cfg)["enqueued_missing"] == 1
    outbox.process_once(session, dispatchers)
    assert len(fake.notes) == 1
