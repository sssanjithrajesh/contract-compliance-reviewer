"""MCP server: the document store and review queue.

    uv run ccr-mcp-documents          # stdio transport, for Claude Desktop / Cursor / any MCP client

Tools mirror the web app one to one so an agent and a human see the same state.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from reviewer.app import db, service
from reviewer.chunking import chunk_text
from reviewer.clauses import CLAUSE_TYPES
from reviewer.config import current_customer
from reviewer.ingest import IngestError
from reviewer.mcp.common import guarded
from reviewer.retrieval import Index


def build(session_factory=None, cfg_getter=current_customer) -> MCPServer:
    from reviewer.integrations import outbox as _  # noqa: F401  register table

    session_factory = session_factory or db.make_session_factory()
    server = MCPServer(
        "ccr-documents",
        instructions=(
            "Contract review document store. Findings are proposals until a named person decides. "
            "Never present a 'proposed' finding to a client as final."
        ),
    )

    @server.tool(description="List uploaded contracts with the status of their latest review.")
    @guarded("list_contracts", cfg_getter)
    def list_contracts(limit: int = 20) -> dict:
        with session_factory() as s:
            rows = s.scalars(select(db.Contract).order_by(db.Contract.created_at.desc()).limit(limit)).all()
            out = []
            for c in rows:
                latest = c.reviews[-1] if c.reviews else None
                out.append(
                    {
                        "contract_id": c.id,
                        "filename": c.filename,
                        "uploaded_at": c.created_at.isoformat(),
                        "review": service.review_summary(latest) if latest else None,
                    }
                )
            return {"status": "ok", "contracts": out}

    @server.tool(
        description="Get the latest review for a contract: every clause finding with citations and decision status."
    )
    @guarded("get_review", cfg_getter)
    def get_review(contract_id: int) -> dict:
        with session_factory() as s:
            c = s.get(db.Contract, contract_id)
            if c is None or not c.reviews:
                return {"status": "not_found", "contract_id": contract_id}
            return service.export_review(c.reviews[-1])

    @server.tool(
        description="Upload contract text and run the configured review engine. Returns the proposed findings."
    )
    @guarded("review_contract", cfg_getter)
    def review_contract(filename: str, text: str) -> dict:
        cfg = cfg_getter()
        with session_factory() as s:
            try:
                contract = service.store_contract(s, text.encode("utf-8"), filename)
            except IngestError as exc:
                return {"status": "error", "reason": str(exc)}
            review = service.run_review(s, contract, cfg.engine, cfg.clauses)
            return {"status": "ok", "contract_id": contract.id, **service.export_review(review)}

    @server.tool(
        description="Lexical search inside one contract. Returns the best-matching passages with character offsets."
    )
    @guarded("search_contract", cfg_getter)
    def search_contract(contract_id: int, query: str, k: int = 3) -> dict:
        with session_factory() as s:
            c = s.get(db.Contract, contract_id)
            if c is None:
                return {"status": "not_found", "contract_id": contract_id}
            index = Index(chunk_text(c.text), mode="bm25")  # fast path; hybrid available via engine
            hits = index.search(query, k=k)
            return {
                "status": "ok",
                "passages": [
                    {
                        "start": h.chunk.start,
                        "end": h.chunk.end,
                        "score": round(h.score, 3),
                        "text": h.chunk.text,
                    }
                    for h in hits
                ],
            }

    @server.tool(description="Approve or reject a finding as a named person. Partners only.")
    @guarded("decide_finding", cfg_getter)
    def decide_finding(finding_id: int, status: str, who: str, note: str = "") -> dict:
        cfg = cfg_getter()
        if cfg.review.require_named_approver and status != "proposed" and not who.strip():
            return {"status": "error", "reason": "a named approver is required"}
        with session_factory() as s:
            try:
                f = service.decide(s, finding_id, status, who, note)
            except (LookupError, ValueError) as exc:
                return {"status": "error", "reason": str(exc)}
            return {
                "status": "ok",
                "finding_id": f.id,
                "clause_type": f.clause_type,
                "decision": f.status,
                "by": f.decided_by,
            }

    @server.tool(description="The clause checklist this deployment runs, with the plain-English question for each.")
    @guarded("list_contracts", cfg_getter)
    def list_clause_types() -> dict:
        cfg = cfg_getter()
        return {
            "status": "ok",
            "clauses": [
                {
                    "slug": slug,
                    "name": CLAUSE_TYPES[slug].cuad_name,
                    "question": CLAUSE_TYPES[slug].question,
                }
                for slug in cfg.clauses
            ],
        }

    return server


def main() -> None:
    build().run(transport="stdio")
