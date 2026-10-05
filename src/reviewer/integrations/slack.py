"""Slack: outbound notifications via incoming webhook, inbound request verification.

Outbound goes through the outbox like everything else. Inbound (a future "approve from
Slack" button) must verify Slack's signature: HMAC-SHA256 over "v0:<timestamp>:<body>"
with the app's signing secret, compared in constant time, and the timestamp must be
within five minutes to defeat replay. That check is here even though the inbound
endpoint is not yet wired, because it is the part people get wrong.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from reviewer.integrations.http import Client, PermanentError


class Slack:
    def __init__(self, webhook_url: str, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        # Webhook URLs are full URLs; split so the shared client can keep a base_url.
        self.webhook_url = webhook_url
        self.client = Client("https://hooks.slack.com", transport=transport, sleep=sleep)

    def notify(self, text: str, blocks: list[dict] | None = None) -> str:
        payload: dict = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        r = self.client.post(self.webhook_url, json=payload)
        # Slack webhooks return the literal string "ok" on success.
        if r.text.strip() != "ok":
            raise PermanentError(f"slack webhook returned {r.text[:100]!r}")
        return "ok"


def verify_signature(
    signing_secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None
) -> bool:
    """Slack request signing (v0). Constant-time compare, 5-minute replay window.

    Testing note: when writing a negative test, build the bad signature so it is provably
    different from the good one (flip a specific character), not probably different.
    See docs/postmortems/2026-09-flaky-signature-test.md.
    """
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs((now or time.time()) - ts) > 300:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def review_created_message(contract: str, url: str, summary: dict, present: int) -> tuple[str, list[dict]]:
    text = f"New contract review: {contract} - {present} of {summary['total']} clauses found, awaiting decisions."
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*New contract review:* <{url}|{contract}>"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{present}/{summary['total']} clauses proposed present",
                },
                {"type": "mrkdwn", "text": f"{summary['proposed']} awaiting a named decision"},
            ],
        },
    ]
    return text, blocks


def review_final_message(contract: str, url: str, summary: dict) -> tuple[str, list[dict]]:
    text = f"Review final: {contract} - {summary['approved']} approved, {summary['rejected']} rejected."
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Review final:* <{url}|{contract}>"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{summary['approved']} approved, {summary['rejected']} rejected",
                },
                {"type": "mrkdwn", "text": "Findings written back to the matter record."},
            ],
        },
    ]
    return text, blocks


def make_dispatcher(slack: Slack):
    def dispatch(kind: str, key: str, payload: dict) -> str:
        if kind != "notify":
            raise PermanentError(f"slack dispatcher does not handle kind {kind!r}")
        return slack.notify(payload["text"], payload.get("blocks"))

    return dispatch
