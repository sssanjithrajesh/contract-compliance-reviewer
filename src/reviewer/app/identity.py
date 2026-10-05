"""Who is approving? Resolve the reviewer's identity from the configured source.

In a pilot the reviewer types their name. In production the app sits behind the customer's
SSO proxy, which strips any client-supplied identity header and injects the authenticated
user. The app never validates tokens itself: that is the proxy's job, and doing it twice
badly is worse than doing it once well (see ADR-0004).

CCR_IDENTITY_MODE overrides the customer config (useful when the same image is deployed
behind a proxy in one environment and without one in another).
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from reviewer.config import CustomerConfig


def resolve_identity(request: Request, cfg: CustomerConfig, typed_name: str = "") -> str:
    mode = os.environ.get("CCR_IDENTITY_MODE") or cfg.access.identity.mode
    if mode == "proxy_header":
        header = os.environ.get("CCR_IDENTITY_HEADER") or cfg.access.identity.header
        who = (request.headers.get(header) or "").strip()
        if not who:
            raise HTTPException(status_code=401, detail=f"no authenticated user ({header} header missing)")
        return who[:100]
    if mode == "form":
        return typed_name.strip()[:100]
    raise HTTPException(status_code=500, detail=f"unknown identity mode {mode!r}")
