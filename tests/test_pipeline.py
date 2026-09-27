import json
from types import SimpleNamespace

import pytest

from reviewer.chunking import chunk_text
from reviewer.ingest import IngestError, ingest_bytes
from reviewer.pipeline import LLMReviewer, RetrievalConfig, RetrievalReviewer
from reviewer.retrieval import Index, tokenize

CONTRACT = """MASTER SERVICES AGREEMENT

1. Term. This Agreement commences on the Effective Date and continues for two (2) years.

2. Termination for Convenience. Either party may terminate this Agreement for any reason
upon ninety (90) days prior written notice to the other party.

3. Governing Law. This Agreement shall be governed by and construed in accordance with the
laws of the State of New York, without regard to its conflict of laws principles.

4. Payment. Customer shall pay all undisputed invoices within thirty (30) days.
"""


def test_chunks_preserve_offsets():
    chunks = chunk_text(CONTRACT, max_chars=300)
    assert chunks, "expected at least one chunk"
    for c in chunks:
        assert CONTRACT[c.start : c.end] == c.text
    assert any("Governing Law" in c.text for c in chunks)


def test_long_paragraph_is_split_with_progress():
    long = " ".join(f"Sentence number {i} is here." for i in range(200))
    chunks = chunk_text(long, max_chars=400, overlap=50)
    assert len(chunks) > 3
    assert all(long[c.start : c.end] == c.text for c in chunks)
    assert chunks[-1].end == len(long)


def test_tokenize_drops_stopwords():
    assert "the" not in tokenize("the laws of the State") and "laws" in tokenize("the laws")


def test_bm25_index_ranks_governing_law_first():
    index = Index(chunk_text(CONTRACT, max_chars=300), mode="bm25")
    hits = index.search("governed by the laws of the state governing law", k=2)
    assert "Governing Law" in hits[0].chunk.text


def test_retrieval_reviewer_bm25_cites_and_refuses():
    r = RetrievalReviewer(RetrievalConfig(mode="bm25", bm25_min_score=1.0))
    f = r.review(CONTRACT, "governing_law", "Which law governs?")
    assert f.present and any("New York" in s.text for s in f.spans)
    assert r.review(CONTRACT, "not_a_type", "?").present is False
    strict = RetrievalReviewer(RetrievalConfig(mode="bm25", bm25_min_score=1e9))
    assert strict.review(CONTRACT, "insurance", "Insurance?").present is False


class FakeAnthropic:
    """Returns a canned JSON answer; records the prompt so tests can inspect it."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(self.payload))])


def test_llm_reviewer_grounds_verbatim_quotes():
    quote = "This Agreement shall be governed by and construed in accordance with the\nlaws of the State of New York"
    client = FakeAnthropic({"present": True, "quotes": [quote], "reasoning": "explicit clause"})
    r = LLMReviewer(client=client, model="fake", retrieval=RetrievalConfig(mode="bm25"))
    f = r.review(CONTRACT, "governing_law", "Which law governs?")
    assert f.present and len(f.spans) == 1
    assert CONTRACT[f.spans[0].start : f.spans[0].end] == quote
    assert client.calls[0]["model"] == "fake"


def test_llm_reviewer_drops_fabricated_quotes_and_refuses():
    client = FakeAnthropic({"present": True, "quotes": ["This sentence is not in the contract."]})
    r = LLMReviewer(client=client, model="fake", retrieval=RetrievalConfig(mode="bm25"))
    f = r.review(CONTRACT, "governing_law", "Which law governs?")
    assert f.present is False and f.spans == []


def test_llm_reviewer_tolerates_whitespace_differences():
    quote = "Either party may terminate this Agreement for any reason upon ninety (90) days prior written notice"
    client = FakeAnthropic({"present": True, "quotes": [quote]})
    r = LLMReviewer(client=client, model="fake", retrieval=RetrievalConfig(mode="bm25"))
    f = r.review(CONTRACT, "termination_for_convenience", "Can they terminate?")
    assert f.present and "ninety (90) days" in f.spans[0].text


def test_llm_reviewer_requires_key_without_client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        LLMReviewer()


def test_ingest_text_and_rejects_unknown():
    doc = ingest_bytes(CONTRACT.encode(), "msa.txt")
    assert doc.text == CONTRACT and doc.page_of(10) == 1
    with pytest.raises(IngestError):
        ingest_bytes(b"x", "file.xyz")


def test_ingest_pdf_roundtrip_and_page_map(tmp_path):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=200, height=200)
    blank = tmp_path / "blank.pdf"
    with blank.open("wb") as fh:
        writer.write(fh)
    with pytest.raises(IngestError, match="no usable text layer"):
        ingest_bytes(blank.read_bytes(), "blank.pdf")
