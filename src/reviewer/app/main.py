"""HTTP layer. Run with: uv run ccr-serve  (then open http://127.0.0.1:8000)

Environment:
  CCR_REVIEWER   which reviewer to run on upload (default retrieval-hybrid; "llm" needs a key)
  DATABASE_URL   SQLAlchemy URL (default sqlite:///./data/reviewer.db)
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from reviewer.app import db, service
from reviewer.app.identity import resolve_identity
from reviewer.clauses import CLAUSE_TYPES
from reviewer.config import CustomerConfig, current_customer
from reviewer.ingest import IngestError
from reviewer.integrations import sync

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(
    database_url: str | None = None,
    reviewer_name: str | None = None,
    customer: CustomerConfig | None = None,
) -> FastAPI:
    from reviewer.integrations import outbox as _outbox  # noqa: F401  (registers the outbox table)

    cfg = customer or current_customer()
    app = FastAPI(title="Contract Compliance Reviewer", version="0.3.0")
    session_factory = db.make_session_factory(database_url)
    app.state.customer = cfg
    app.state.reviewer_name = reviewer_name or cfg.engine
    app.state.base_url = os.environ.get("CCR_BASE_URL", "http://127.0.0.1:8000")

    def get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "reviewer": app.state.reviewer_name}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, session: Session = Depends(get_session)):
        contracts = session.scalars(select(db.Contract).order_by(db.Contract.created_at.desc())).all()
        rows = []
        for c in contracts:
            latest = c.reviews[-1] if c.reviews else None
            rows.append(
                {
                    "contract": c,
                    "review": latest,
                    "summary": service.review_summary(latest) if latest else None,
                }
            )
        return TEMPLATES.TemplateResponse(request, "index.html", {"rows": rows, "reviewer": app.state.reviewer_name})

    @app.post("/contracts")
    async def upload(file: UploadFile = File(...), session: Session = Depends(get_session)):
        data = await file.read()
        try:
            contract = service.store_contract(session, data, file.filename or "upload")
        except IngestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        review = service.run_review(session, contract, app.state.reviewer_name, cfg.clauses)
        sync.enqueue_review_created(session, cfg, review, app.state.base_url)
        session.commit()
        return RedirectResponse(url=f"/contracts/{contract.id}", status_code=303)

    @app.get("/contracts/{contract_id}", response_class=HTMLResponse)
    def contract_page(contract_id: int, request: Request, session: Session = Depends(get_session)):
        contract = session.get(db.Contract, contract_id)
        if contract is None:
            raise HTTPException(404)
        review = contract.reviews[-1] if contract.reviews else None
        findings = sorted(review.findings, key=lambda f: (f.status != "proposed", f.clause_type)) if review else []
        return TEMPLATES.TemplateResponse(
            request,
            "contract.html",
            {
                "contract": contract,
                "review": review,
                "findings": findings,
                "clauses": CLAUSE_TYPES,
                "summary": service.review_summary(review) if review else None,
            },
        )

    @app.post("/findings/{finding_id}/decide")
    def decide(
        finding_id: int,
        request: Request,
        status: str = Form(...),
        who: str = Form(""),
        note: str = Form(""),
        session: Session = Depends(get_session),
    ):
        who = resolve_identity(request, cfg, who)
        if status != "proposed" and cfg.review.require_named_approver and not who:
            raise HTTPException(status_code=422, detail="a named reviewer is required to approve or reject")
        try:
            finding = service.decide(session, finding_id, status, who, note)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        sync.enqueue_review_final(session, cfg, finding.review, app.state.base_url)
        session.commit()
        return RedirectResponse(url=f"/contracts/{finding.review.contract_id}", status_code=303)

    @app.get("/api/outbox")
    def outbox_status(session: Session = Depends(get_session)):
        from reviewer.integrations.outbox import pending_summary

        return {
            "customer": cfg.customer.id,
            "offline": cfg.offline,
            "outbox": pending_summary(session),
        }

    @app.get("/api/contracts/{contract_id}/review.json")
    def export(contract_id: int, session: Session = Depends(get_session)):
        contract = session.get(db.Contract, contract_id)
        if contract is None or not contract.reviews:
            raise HTTPException(404)
        return JSONResponse(service.export_review(contract.reviews[-1]))

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "reviewer.app.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )
