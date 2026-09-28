"""Customer configuration and runtime settings.

Two sources, deliberately separate:

- The customer YAML (customers/<id>.yaml) says WHAT this deployment does: which clauses,
  which integrations, who may call which tools. It is checked into the repo and reviewed
  like code.
- Environment variables say WHERE and WITH WHAT: database URL, API tokens, offline flag.
  They never go in the repo.

CCR_OFFLINE=1 is the air-gapped switch. It forces the local retrieval engine and makes
every outbound HTTP client refuse to connect, so a misconfiguration fails loudly instead
of leaking a document.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from reviewer.clauses import CLAUSE_TYPES

CUSTOMERS_DIR = Path(__file__).resolve().parent.parent.parent / "customers"


class CustomerInfo(BaseModel):
    id: str
    name: str
    domain: str = "legal"
    tagline: str = ""


class ReviewSettings(BaseModel):
    engine: str = "retrieval-hybrid"
    offline: bool = False
    require_named_approver: bool = True


class CRMSettings(BaseModel):
    provider: str = "none"
    matter_object: str = "deals"
    write_back_on: str = "approved"


class NotifySettings(BaseModel):
    provider: str = "none"
    channel_hint: str = ""
    notify_on: list[str] = Field(default_factory=list)


class Integrations(BaseModel):
    crm: CRMSettings = Field(default_factory=CRMSettings)
    notify: NotifySettings = Field(default_factory=NotifySettings)


class Identity(BaseModel):
    """Where the approver's name comes from.

    form          the reviewer types their name (demo / pilot default)
    proxy_header  an SSO proxy (oauth2-proxy, Cloudflare Access, ALB+OIDC) sits in front of
                  the app and injects the authenticated user in a header; the typed name is ignored
    """

    mode: str = "form"
    header: str = "X-Forwarded-User"


class Access(BaseModel):
    roles: dict[str, list[str]] = Field(default_factory=dict)
    identity: Identity = Field(default_factory=Identity)

    def allowed(self, role: str, tool: str) -> bool:
        return tool in self.roles.get(role, [])


class ROI(BaseModel):
    contracts_per_year: int = 0
    junior_hours_before: float = 0
    junior_hours_after: float = 0
    senior_hours_before: float = 0
    senior_hours_after: float = 0

    def hours_saved_per_year(self) -> dict[str, float]:
        n = self.contracts_per_year
        return {
            "junior": round(n * (self.junior_hours_before - self.junior_hours_after), 1),
            "senior": round(n * (self.senior_hours_before - self.senior_hours_after), 1),
        }


class CustomerConfig(BaseModel):
    customer: CustomerInfo
    clauses: list[str]
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    integrations: Integrations = Field(default_factory=Integrations)
    access: Access = Field(default_factory=Access)
    roi: ROI = Field(default_factory=ROI)

    def model_post_init(self, __context) -> None:
        unknown = [c for c in self.clauses if c not in CLAUSE_TYPES]
        if unknown:
            raise ValueError(f"unknown clause slugs in customer config: {unknown}")

    @property
    def offline(self) -> bool:
        return self.review.offline or os.environ.get("CCR_OFFLINE", "") in ("1", "true", "yes")

    @property
    def engine(self) -> str:
        if self.offline and self.review.engine == "llm":
            return "retrieval-hybrid"
        return os.environ.get("CCR_REVIEWER") or self.review.engine


def load_customer(path_or_id: str | Path | None = None) -> CustomerConfig:
    if path_or_id is None:
        path_or_id = os.environ.get("CCR_CUSTOMER", "harlow-pryce")
    path = Path(path_or_id)
    if not path.suffix:
        path = CUSTOMERS_DIR / f"{path_or_id}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CustomerConfig.model_validate(raw)


@lru_cache(maxsize=1)
def current_customer() -> CustomerConfig:
    return load_customer()


class Secrets:
    """Read-once accessors for environment secrets. Missing values raise with a clear name."""

    @staticmethod
    def get(name: str, required: bool = True) -> str | None:
        value = os.environ.get(name)
        if required and not value:
            raise RuntimeError(f"{name} is not set; see .env.example")
        return value

    HUBSPOT_TOKEN = "HUBSPOT_PRIVATE_APP_TOKEN"
    SLACK_WEBHOOK = "SLACK_WEBHOOK_URL"
    SLACK_SIGNING_SECRET = "SLACK_SIGNING_SECRET"
    ANTHROPIC = "ANTHROPIC_API_KEY"
