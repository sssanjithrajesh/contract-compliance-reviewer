"""MCP servers exposing the reviewer to agents and other tools.

Three servers, deliberately separate so a customer can grant an agent the document
tools without the CRM tools:

- documents  list/review/search contracts, record decisions
- crm        look up matters, write findings back, reconcile (HubSpot)
- notify     post to the firm's channel (Slack)

Access control is per tool per role, declared in the customer YAML, enforced here.
Every tool that touches an external system returns {"status": "unavailable", ...}
instead of raising when that system is down, rate-limited, or blocked by offline mode.
"""
