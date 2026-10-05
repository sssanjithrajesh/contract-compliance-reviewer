"""Phase 4: a second customer (healthcare BAA review) runs on the same code via config only,
and approver identity can come from an SSO proxy header instead of a typed name."""

from pathlib import Path

from fastapi.testclient import TestClient

from evals.run import run as run_evals
from evals.schema import load_cases
from reviewer.app.main import create_app
from reviewer.clauses import CLAUSE_TYPES
from reviewer.config import load_customer
from tests.test_app import _first_finding_id
from tests.test_pipeline import CONTRACT

ROOT = Path(__file__).resolve().parent.parent
BAA = (ROOT / "evals" / "contracts" / "hhs-sample-baa.txt").read_text(encoding="utf-8")


def test_meridian_config_uses_only_baa_clauses():
    cfg = load_customer("meridian-health")
    assert cfg.customer.domain == "healthcare"
    assert cfg.clauses and all(slug.startswith("baa_") for slug in cfg.clauses)
    assert set(cfg.clauses) <= set(CLAUSE_TYPES)
    assert cfg.offline and cfg.engine == "retrieval-hybrid"


def test_customer_filter_partitions_eval_set():
    all_cases = load_cases(ROOT / "evals" / "cases")
    legal = {c.clause_type for c in all_cases if not c.clause_type.startswith("baa_")}
    health = [c for c in all_cases if c.clause_type.startswith("baa_")]
    assert len(health) == 16
    assert sum(c.expected.present for c in health) == 11
    # Nothing the gate tracks is a healthcare clause, so adding meridian cases cannot move the gate.
    assert legal.isdisjoint({c.clause_type for c in health})


def test_meridian_eval_run_hybrid_beats_keyword_on_deficient_baa():
    # The deficient vendor addendum is where a naive reviewer invents clauses that are not there.
    keyword = run_evals("keyword", "meridian-health")
    hybrid = run_evals("retrieval-hybrid", "meridian-health")
    assert keyword.overall.n == hybrid.overall.n == 16
    assert hybrid.overall.hallucinated_presence_rate <= 0.2
    assert hybrid.overall.hallucinated_presence_rate < keyword.overall.hallucinated_presence_rate
    assert hybrid.overall.presence_accuracy >= 0.85


def test_meridian_app_reviews_only_baa_clauses(tmp_path):
    cfg = load_customer("meridian-health")
    app = create_app(database_url=f"sqlite:///{tmp_path / 'm.db'}", reviewer_name="keyword", customer=cfg)
    with TestClient(app) as client:
        r = client.post("/contracts", files={"file": ("baa.txt", BAA.encode(), "text/plain")}, follow_redirects=False)
        contract_id = int(r.headers["location"].rsplit("/", 1)[-1])
        export = client.get(f"/api/contracts/{contract_id}/review.json").json()
        assert export["summary"]["total"] == len(cfg.clauses)
        assert {f["clause_type"] for f in export["findings"]} == set(cfg.clauses)
        hhs = next(f for f in export["findings"] if f["clause_type"] == "baa_hhs_access")
        assert hhs["present"] and any("Secretary" in c["text"] for c in hhs["citations"])


def test_proxy_header_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("CCR_IDENTITY_MODE", "proxy_header")
    monkeypatch.setenv("CCR_IDENTITY_HEADER", "X-Forwarded-User")
    app = create_app(database_url=f"sqlite:///{tmp_path / 'p.db'}", reviewer_name="keyword")
    with TestClient(app) as client:
        r = client.post(
            "/contracts", files={"file": ("msa.txt", CONTRACT.encode(), "text/plain")}, follow_redirects=False
        )
        contract_id = int(r.headers["location"].rsplit("/", 1)[-1])
        finding_id = _first_finding_id(client, contract_id)

        # A typed name is not trusted when the proxy is the identity source.
        r = client.post(f"/findings/{finding_id}/decide", data={"status": "approved", "who": "Mallory"})
        assert r.status_code == 401

        r = client.post(
            f"/findings/{finding_id}/decide",
            data={"status": "approved", "who": "Mallory"},
            headers={"X-Forwarded-User": "a.harlow@harlowpryce.example"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        export = client.get(f"/api/contracts/{contract_id}/review.json").json()
        decided = [f for f in export["findings"] if f["status"] == "approved"]
        assert len(decided) == 1 and decided[0]["decided_by"] == "a.harlow@harlowpryce.example"
