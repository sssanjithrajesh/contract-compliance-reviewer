"""Shared plumbing for the MCP servers: role resolution, access checks, degradation."""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from typing import Any

from reviewer.config import CustomerConfig, current_customer
from reviewer.integrations.http import OfflineError, PermanentError, RetryableError


class AccessDenied(PermissionError):
    pass


def current_role() -> str:
    """Pilot: role comes from the environment the MCP client was launched with.
    Production: replaced by an OIDC claim on the transport (see docs/integrations.md)."""
    return os.environ.get("CCR_MCP_ROLE", "associate")


def guarded(tool_name: str, cfg_getter: Callable[[], CustomerConfig] = current_customer):
    """Decorator: enforce role access and convert integration failures into status dicts."""

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs) -> Any:
            cfg = cfg_getter()
            role = current_role()
            if not cfg.access.allowed(role, tool_name):
                return {
                    "status": "denied",
                    "tool": tool_name,
                    "role": role,
                    "reason": f"role {role!r} may not call {tool_name}; see customers/{cfg.customer.id}.yaml",
                }
            try:
                return fn(*args, **kwargs)
            except OfflineError as exc:
                return {
                    "status": "unavailable",
                    "reason": "offline mode",
                    "detail": str(exc),
                    "retry": False,
                }
            except RetryableError as exc:
                return {
                    "status": "unavailable",
                    "reason": "upstream unavailable or rate limited",
                    "detail": str(exc),
                    "retry": True,
                    "retry_after_seconds": exc.retry_after,
                }
            except PermanentError as exc:
                return {
                    "status": "error",
                    "reason": "upstream rejected the request",
                    "detail": str(exc),
                    "retry": False,
                }
            except RuntimeError as exc:  # e.g. missing secret
                return {
                    "status": "unavailable",
                    "reason": "not configured",
                    "detail": str(exc),
                    "retry": False,
                }

        return inner

    return wrap
