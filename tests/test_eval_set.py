"""Guards on the committed eval set itself. If these fail, the spec is broken."""

from evals.schema import CASES_DIR, CONTRACTS_DIR, load_cases, validate_against_contracts
from reviewer.baselines import AlwaysAbsent, KeywordBaseline
from reviewer.clauses import CLAUSE_TYPES
from reviewer.interfaces import Finding, Reviewer


def test_eval_set_is_large_enough_and_balanced():
    cases = load_cases(CASES_DIR)
    assert len(cases) >= 100, f"only {len(cases)} cases; the spec needs 100+"
    present = sum(c.expected.present for c in cases)
    assert 0.3 <= present / len(cases) <= 0.8, "need a real mix of present and absent clauses"


def test_every_span_matches_its_contract():
    problems = validate_against_contracts(load_cases(CASES_DIR), CONTRACTS_DIR)
    assert problems == [], "\n".join(problems[:10])


def test_all_clause_types_are_known_and_covered():
    cases = load_cases(CASES_DIR)
    used = {c.clause_type for c in cases}
    assert used <= set(CLAUSE_TYPES), used - set(CLAUSE_TYPES)
    assert len(used) >= 12, f"only {len(used)} clause types covered"


def test_case_ids_are_unique():
    ids = [c.id for c in load_cases(CASES_DIR)]
    assert len(ids) == len(set(ids))


def test_baselines_satisfy_protocol_and_return_findings():
    text = "This Agreement shall be governed by the laws of England."
    for reviewer in (KeywordBaseline(), AlwaysAbsent()):
        assert isinstance(reviewer, Reviewer)
        f = reviewer.review(text, "governing_law", "Which law?")
        assert isinstance(f, Finding)
    kb = KeywordBaseline().review(text, "governing_law", "Which law?")
    assert kb.present and kb.spans and "governed by" in kb.spans[0].text
    assert KeywordBaseline().review(text, "not_a_type", "?").present is False
