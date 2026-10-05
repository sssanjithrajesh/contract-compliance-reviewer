"""Durable outbox for writes to external systems.

Pattern: the app never calls HubSpot or Slack directly on a user action. It writes an
outbox row in the same transaction as the user's decision, and a worker drains the outbox.

Why: a lawyer clicking Approve while HubSpot is rate-limiting us must still see Approve
succeed. The write-back happens seconds later, or minutes later, and is idempotent so
retries and reconciliation cannot duplicate a note.

Idempotency key = f"{target}:{kind}:{entity id}". Dispatchers embed it in the remote
payload so a crash between "remote succeeded" and "row marked sent" is recoverable: the
reconciliation job asks the remote system whether the key already exists.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from reviewer.app.db import Base
from reviewer.integrations.http import OfflineError, PermanentError, RetryableError

MAX_ATTEMPTS = 8


def _now() -> datetime:
    return datetime.now(UTC)


class OutboxItem(Base):
    __tablename__ = "integration_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(30))  # hubspot | slack
    kind: Mapped[str] = mapped_column(String(50))  # write_findings | notify
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    payload: Mapped[str] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|sent|failed|skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remote_id: Mapped[str] = mapped_column(String(200), default="")


def enqueue(session: Session, target: str, kind: str, idempotency_key: str, payload: dict) -> OutboxItem | None:
    """Add a row unless one with the same key exists. Caller commits."""
    existing = session.scalar(select(OutboxItem).where(OutboxItem.idempotency_key == idempotency_key))
    if existing is not None:
        return None
    item = OutboxItem(target=target, kind=kind, idempotency_key=idempotency_key, payload=json.dumps(payload))
    session.add(item)
    return item


Dispatcher = Callable[[str, str, dict], str]
"""(kind, idempotency_key, payload) -> remote id. Raise RetryableError / PermanentError / OfflineError."""


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def process_once(
    session: Session,
    dispatchers: dict[str, Dispatcher],
    now: datetime | None = None,
    limit: int = 50,
) -> dict:
    """Drain due items once. Returns counts. Safe to run from cron, a loop, or a test."""
    now = now or _now()
    due = session.scalars(
        select(OutboxItem).where(OutboxItem.status == "pending").order_by(OutboxItem.next_attempt_at).limit(limit)
    ).all()
    due = [item for item in due if _aware(item.next_attempt_at) <= now]
    counts = {"sent": 0, "retried": 0, "failed": 0, "skipped": 0}
    for item in due:
        dispatcher = dispatchers.get(item.target)
        if dispatcher is None:
            item.status, item.last_error = "skipped", f"no dispatcher for target {item.target!r}"
            counts["skipped"] += 1
            continue
        item.attempts += 1
        try:
            item.remote_id = dispatcher(item.kind, item.idempotency_key, json.loads(item.payload)) or ""
        except OfflineError as exc:
            # Not an error: offline deployments keep the row pending so a later online sync delivers it.
            item.last_error = str(exc)
            item.attempts -= 1
            item.next_attempt_at = now + timedelta(minutes=10)
            counts["skipped"] += 1
        except RetryableError as exc:
            item.last_error = str(exc)
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "failed"
                counts["failed"] += 1
            else:
                delay = exc.retry_after or min(3600, 30 * (2 ** (item.attempts - 1)))
                delay *= 1 + random.uniform(-0.2, 0.2)  # noqa: S311
                item.next_attempt_at = now + timedelta(seconds=delay)
                counts["retried"] += 1
        except PermanentError as exc:
            item.status, item.last_error = "failed", str(exc)
            counts["failed"] += 1
        else:
            item.status, item.sent_at, item.last_error = "sent", now, ""
            counts["sent"] += 1
    session.commit()
    return counts


def pending_summary(session: Session) -> dict[str, int]:
    rows = session.scalars(select(OutboxItem)).all()
    out: dict[str, int] = {}
    for r in rows:
        out[r.status] = out.get(r.status, 0) + 1
    return out
