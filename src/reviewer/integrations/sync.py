"""Wire the outbox to real dispatchers, and reconcile.

    uv run ccr-sync            # drain due outbox items once, then reconcile
    uv run ccr-sync --loop 30  # keep draining every 30 seconds

Reconciliation answers "did anything fall through the cracks?": every final review must
have a sent HubSpot write-back; every failed item older than a day gets one more chance.
It is idempotent, so running it twice is harmless.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from reviewer.app import db, service
from reviewer.config import CustomerConfig, Secrets, current_customer
from reviewer.integrations import hubspot as hs
from reviewer.integrations import outbox
from reviewer.integrations import slack as sl


def build_dispatchers(cfg: CustomerConfig, transport=None) -> dict[str, outbox.Dispatcher]:
    dispatchers: dict[str, outbox.Dispatcher] = {}
    if cfg.integrations.crm.provider == "hubspot":
        token = Secrets.get(Secrets.HUBSPOT_TOKEN, required=False)
        if token:
            dispatchers["hubspot"] = hs.make_dispatcher(hs.HubSpot(token, transport=transport))
    if cfg.integrations.notify.provider == "slack":
        url = Secrets.get(Secrets.SLACK_WEBHOOK, required=False)
        if url:
            dispatchers["slack"] = sl.make_dispatcher(sl.Slack(url, transport=transport))
    return dispatchers


def enqueue_review_created(session: Session, cfg: CustomerConfig, review: db.Review, base_url: str) -> None:
    if cfg.integrations.notify.provider != "slack" or "review_created" not in cfg.integrations.notify.notify_on:
        return
    summary = service.review_summary(review)
    present = sum(1 for f in review.findings if f.present)
    url = f"{base_url}/contracts/{review.contract_id}"
    text, blocks = sl.review_created_message(review.contract.filename, url, summary, present)
    outbox.enqueue(
        session,
        "slack",
        "notify",
        f"slack:review_created:{review.id}",
        {"text": text, "blocks": blocks},
    )


def enqueue_review_final(session: Session, cfg: CustomerConfig, review: db.Review, base_url: str) -> None:
    """Called after every decision; only does work when the review has just become final."""
    summary = service.review_summary(review)
    if not summary["final"]:
        return
    if cfg.integrations.crm.provider == "hubspot":
        outbox.enqueue(
            session,
            "hubspot",
            "write_findings",
            f"hubspot:write_findings:{review.id}",
            {
                "matter_name": _matter_name(review.contract.filename),
                "review": service.export_review(review),
            },
        )
    if cfg.integrations.notify.provider == "slack" and "review_final" in cfg.integrations.notify.notify_on:
        url = f"{base_url}/contracts/{review.contract_id}"
        text, blocks = sl.review_final_message(review.contract.filename, url, summary)
        outbox.enqueue(
            session,
            "slack",
            "notify",
            f"slack:review_final:{review.id}",
            {"text": text, "blocks": blocks},
        )


def _matter_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return stem.replace("-", " ").replace("_", " ").strip().title()


def reconcile(session: Session, cfg: CustomerConfig, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    counts = {"enqueued_missing": 0, "reopened_failed": 0}
    if cfg.integrations.crm.provider == "hubspot":
        for review in session.scalars(select(db.Review)).all():
            if not service.review_summary(review)["final"]:
                continue
            key = f"hubspot:write_findings:{review.id}"
            row = session.scalar(select(outbox.OutboxItem).where(outbox.OutboxItem.idempotency_key == key))
            if row is None:
                enqueue_review_final(session, cfg, review, os.environ.get("CCR_BASE_URL", "http://localhost:8000"))
                counts["enqueued_missing"] += 1
    stale = now - timedelta(days=1)
    for item in session.scalars(select(outbox.OutboxItem).where(outbox.OutboxItem.status == "failed")).all():
        created = item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=UTC)
        if created < stale and item.attempts < outbox.MAX_ATTEMPTS * 2:
            item.status, item.next_attempt_at = "pending", now
            counts["reopened_failed"] += 1
    session.commit()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--loop", type=int, default=0, help="seconds between passes; 0 = run once")
    args = parser.parse_args(argv)
    cfg = current_customer()
    factory = db.make_session_factory()
    dispatchers = build_dispatchers(cfg)
    if not dispatchers:
        print("no dispatchers configured (missing tokens or providers set to none); outbox will accumulate")
    while True:
        with factory() as session:
            drained = outbox.process_once(session, dispatchers)
            fixed = reconcile(session, cfg)
            print(
                f"{datetime.now(UTC).isoformat(timespec='seconds')} outbox={drained} reconcile={fixed} "
                f"pending_by_status={outbox.pending_summary(session)}"
            )
        if not args.loop:
            return 0
        time.sleep(args.loop)
