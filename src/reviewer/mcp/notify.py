"""MCP server: notifications to the firm's channel (Slack).

    uv run ccr-mcp-notify

Messages are queued through the outbox so an agent's notification survives a Slack outage.
"""

from __future__ import annotations

import hashlib

from mcp.server.mcpserver import MCPServer

from reviewer.app import db
from reviewer.config import current_customer
from reviewer.integrations import outbox
from reviewer.mcp.common import guarded


def build(session_factory=None, cfg_getter=current_customer) -> MCPServer:
    from reviewer.integrations import outbox as _  # noqa: F401  register table

    session_factory = session_factory or db.make_session_factory()
    server = MCPServer(
        "ccr-notify",
        instructions="Post to the firm's contract-review channel. Messages are queued.",
    )

    @server.tool(description="Queue a message to the configured channel. Identical text within a day is sent once.")
    @guarded("notify_channel", cfg_getter)
    def notify_channel(text: str) -> dict:
        cfg = cfg_getter()
        if cfg.integrations.notify.provider != "slack":
            return {"status": "unavailable", "reason": "no notification provider configured"}
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        with session_factory() as s:
            item = outbox.enqueue(s, "slack", "notify", f"slack:manual:{digest}", {"text": text})
            s.commit()
            return {
                "status": "queued" if item else "duplicate",
                "channel": cfg.integrations.notify.channel_hint,
            }

    return server


def main() -> None:
    build().run(transport="stdio")
