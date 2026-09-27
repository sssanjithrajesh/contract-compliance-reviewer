import json
from types import SimpleNamespace

from reviewer.agents import ObligationChecker, ReviewOrchestrator, RiskSummarizer
from reviewer.baselines import KeywordBaseline
from reviewer.config import load_customer
from tests.test_pipeline import CONTRACT

CLAUSES = load_customer("harlow-pryce").clauses


def test_orchestrator_offline_produces_packet_without_inventing_citations():
    packet = ReviewOrchestrator(KeywordBaseline(), CLAUSES).run("msa.txt", CONTRACT)
    assert set(packet.findings) == set(CLAUSES)
    assert packet.used_llm is False and packet.engine == "keyword"
    # every obligation points inside a span the extractor produced
    spans = [(s.start, s.end) for f in packet.findings.values() for s in f.spans]
    for o in packet.obligations:
        assert any(a <= o.source_start and o.source_end <= b for a, b in spans)
    assert "pending a named lawyer" in packet.summary
    assert packet.risks[0].severity in {"high", "medium", "low"}
    d = packet.as_dict()
    assert json.dumps(d)  # serialisable


def test_obligation_rules_find_party_action_deadline():
    text = "Customer shall pay all undisputed invoices within thirty (30) days of receipt."
    from reviewer.interfaces import Finding, Span

    findings = {"minimum_commitment": Finding(present=True, spans=[Span(start=0, end=len(text), text=text)])}
    obs = ObligationChecker().run(text, findings)
    assert obs and obs[0].party == "Customer" and obs[0].deadline.startswith("within thirty")


def test_risk_ranking_puts_absent_liability_cap_high():
    from reviewer.interfaces import Finding, Span

    findings = {
        "cap_on_liability": Finding.absent(),
        "governing_law": Finding(present=True, spans=[Span(start=0, end=5, text="x" * 5)], confidence=0.9),
        "uncapped_liability": Finding(present=True, spans=[Span(start=0, end=5, text="x" * 5)], confidence=0.4),
    }
    risks = RiskSummarizer().rank(findings)
    assert risks[0].severity == "high" and risks[0].clause_type in {
        "cap_on_liability",
        "uncapped_liability",
    }
    assert [r.clause_type for r in risks if r.severity == "low"] == ["governing_law"]


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(text=self.reply)]))


def test_llm_refinement_cannot_add_obligations_with_unknown_offsets():
    text = "Supplier shall deliver the goods within ten (10) days."
    from reviewer.interfaces import Finding, Span

    findings = {"minimum_commitment": Finding(present=True, spans=[Span(start=0, end=len(text), text=text)])}
    fabricated = json.dumps(
        [
            {
                "clause_type": "minimum_commitment",
                "party": "Supplier",
                "action": "shall deliver the goods within ten (10) days",
                "deadline": "within ten (10) days",
                "source_start": 0,
                "source_end": 54,
            },
            {
                "clause_type": "minimum_commitment",
                "party": "Buyer",
                "action": "shall pay a penalty",
                "deadline": None,
                "source_start": 999,
                "source_end": 1200,
            },
        ]
    )
    obs = ObligationChecker(llm=FakeLLM(fabricated)).run(text, findings)
    assert [o.party for o in obs] == ["Supplier"]


def test_llm_summary_falls_back_on_garbage():
    class Boom:
        messages = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("down")))

    s = RiskSummarizer(llm=Boom()).summarize("c", [], [])
    assert "pending a named lawyer" in s
