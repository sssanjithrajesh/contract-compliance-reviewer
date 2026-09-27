import pytest
from fastapi.testclient import TestClient

from reviewer.app.main import create_app
from tests.test_pipeline import CONTRACT


@pytest.fixture
def client(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'test.db'}", reviewer_name="keyword")
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["reviewer"] == "keyword"


def test_upload_review_decide_export(client):
    r = client.post(
        "/contracts",
        files={"file": ("msa.txt", CONTRACT.encode(), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    url = r.headers["location"]
    page = client.get(url)
    assert page.status_code == 200
    assert "Governing Law" in page.text and "awaiting decision" in page.text

    contract_id = int(url.rsplit("/", 1)[-1])
    export = client.get(f"/api/contracts/{contract_id}/review.json").json()
    assert export["summary"]["total"] == 15 and export["summary"]["proposed"] == 15
    gov = next(f for f in export["findings"] if f["clause_type"] == "governing_law")
    assert gov["present"] and any("New York" in c["text"] for c in gov["citations"])

    # Approving requires a name.
    finding_id = _first_finding_id(client, contract_id)
    r = client.post(f"/findings/{finding_id}/decide", data={"status": "approved", "who": ""})
    assert r.status_code == 422

    r = client.post(
        f"/findings/{finding_id}/decide",
        data={"status": "approved", "who": "A. Harlow", "note": "checked against p.1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    export = client.get(f"/api/contracts/{contract_id}/review.json").json()
    approved = [f for f in export["findings"] if f["status"] == "approved"]
    assert len(approved) == 1 and approved[0]["decided_by"] == "A. Harlow"
    assert export["summary"]["final"] is False


def test_rejects_unsupported_and_scanned_like_files(client):
    r = client.post("/contracts", files={"file": ("x.xyz", b"data", "application/octet-stream")})
    assert r.status_code == 422


def _first_finding_id(client, contract_id: int) -> int:
    html = client.get(f"/contracts/{contract_id}").text
    marker = 'action="/findings/'
    start = html.index(marker) + len(marker)
    return int(html[start : html.index("/", start)])
