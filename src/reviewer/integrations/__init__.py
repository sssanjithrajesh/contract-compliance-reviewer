"""Outbound integrations.

Rule for every module here: a downstream outage must never block a lawyer from reviewing
a contract. Writes go through the outbox (durable, idempotent, retried); reads degrade to
"unavailable" with a reason. See docs/integrations.md for the failure-mode table.
"""
