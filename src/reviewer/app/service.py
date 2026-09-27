"""Application logic, independent of HTTP so it can be tested and reused by MCP tools."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from reviewer.app import db
from reviewer.baselines import get_reviewer
from reviewer.clauses import CLAUSE_TYPES
from reviewer.ingest import Document, ingest_bytes

DECISIONS = {"approved", "rejected", "proposed"}


def store_contract(session: Session, data: bytes, filename: str) -> db.Contract:
    doc: Document = ingest_bytes(data, filename)
    contract = db.Contract(
        filename=doc.filename,
        media_type=doc.media_type,
        text=doc.text,
        page_starts=json.dumps(doc.page_starts),
    )
    session.add(contract)
    session.commit()
    return contract


def run_review(
    session: Session,
    contract: db.Contract,
    reviewer_name: str,
    clause_slugs: list[str] | None = None,
) -> db.Review:
    reviewer = get_reviewer(reviewer_name)
    slugs = clause_slugs or list(CLAUSE_TYPES)
    doc = Document(
        text=contract.text,
        filename=contract.filename,
        media_type=contract.media_type,
        page_starts=json.loads(contract.page_starts),
    )
    review = db.Review(contract_id=contract.id, reviewer_name=reviewer.name)
    session.add(review)
    session.flush()
    for slug in slugs:
        ct = CLAUSE_TYPES[slug]
        finding = reviewer.review(contract.text, slug, ct.question)
        row = db.Finding(
            review_id=review.id,
            clause_type=slug,
            present=int(finding.present),
            rationale=finding.rationale,
            confidence=finding.confidence,
        )
        session.add(row)
        session.flush()
        for span in finding.spans:
            session.add(
                db.Citation(
                    finding_id=row.id,
                    start=span.start,
                    end=span.end,
                    page=doc.page_of(span.start),
                    text=span.text or contract.text[span.start : span.end],
                )
            )
    session.commit()
    return review


def decide(session: Session, finding_id: int, status: str, who: str, note: str = "") -> db.Finding:
    if status not in DECISIONS:
        raise ValueError(f"status must be one of {sorted(DECISIONS)}")
    finding = session.get(db.Finding, finding_id)
    if finding is None:
        raise LookupError(f"finding {finding_id} not found")
    finding.status = status
    finding.decided_by = who.strip() or None
    finding.decided_at = datetime.now(UTC) if status != "proposed" else None
    finding.note = note
    session.commit()
    return finding


def review_summary(review: db.Review) -> dict:
    counts = {"proposed": 0, "approved": 0, "rejected": 0}
    for f in review.findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    return {
        **counts,
        "total": len(review.findings),
        "final": counts["proposed"] == 0 and len(review.findings) > 0,
    }


def export_review(review: db.Review) -> dict:
    return {
        "contract": review.contract.filename,
        "reviewer": review.reviewer_name,
        "created_at": review.created_at.isoformat(),
        "summary": review_summary(review),
        "findings": [
            {
                "clause_type": f.clause_type,
                "question": CLAUSE_TYPES[f.clause_type].question,
                "present": bool(f.present),
                "confidence": f.confidence,
                "status": f.status,
                "decided_by": f.decided_by,
                "decided_at": f.decided_at.isoformat() if f.decided_at else None,
                "note": f.note,
                "citations": [{"page": c.page, "start": c.start, "end": c.end, "text": c.text} for c in f.citations],
            }
            for f in review.findings
        ],
    }
