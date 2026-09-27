"""The clause types this reviewer knows about.

Each entry maps our internal slug to the CUAD category name (so eval cases can be traced
back to the public dataset), a plain-English question a lawyer would actually ask, and
why the clause matters to the business. The `keywords` are used only by the keyword
baseline; the real system does not depend on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClauseType:
    slug: str
    cuad_name: str
    question: str
    why_it_matters: str
    keywords: tuple[str, ...] = field(default_factory=tuple)


CLAUSE_TYPES: dict[str, ClauseType] = {
    ct.slug: ct
    for ct in [
        ClauseType(
            slug="governing_law",
            cuad_name="Governing Law",
            question="Which jurisdiction's law governs this contract?",
            why_it_matters="Determines where disputes are fought and under whose rules.",
            keywords=("governed by", "governing law", "laws of the state", "laws of"),
        ),
        ClauseType(
            slug="termination_for_convenience",
            cuad_name="Termination For Convenience",
            question="Can either party terminate without cause, and on what notice?",
            why_it_matters="A counterparty that can walk away at will changes the risk profile.",
            keywords=("terminate", "for convenience", "without cause", "for any reason"),
        ),
        ClauseType(
            slug="cap_on_liability",
            cuad_name="Cap On Liability",
            question="Is there a cap on either party's liability?",
            why_it_matters="Bounds the maximum financial exposure.",
            keywords=(
                "limitation of liability",
                "liability shall not exceed",
                "in no event",
                "cap",
            ),
        ),
        ClauseType(
            slug="uncapped_liability",
            cuad_name="Uncapped Liability",
            question="Are there carve-outs where liability is uncapped?",
            why_it_matters="Carve-outs (fraud, IP, confidentiality) are the real exposure.",
            keywords=("shall not apply to", "except", "gross negligence", "willful misconduct"),
        ),
        ClauseType(
            slug="non_compete",
            cuad_name="Non-Compete",
            question="Is either party restricted from competing?",
            why_it_matters="Can block future business lines or acquisitions.",
            keywords=("non-compete", "shall not compete", "competing", "competitive"),
        ),
        ClauseType(
            slug="exclusivity",
            cuad_name="Exclusivity",
            question="Does this contract grant exclusivity to either party?",
            why_it_matters="Locks a party into a single supplier or customer.",
            keywords=("exclusive", "exclusively", "sole and exclusive"),
        ),
        ClauseType(
            slug="anti_assignment",
            cuad_name="Anti-Assignment",
            question="Is assignment of the contract restricted?",
            why_it_matters="Affects whether the contract survives a sale or restructuring.",
            keywords=("assign", "assignment", "may not assign", "shall not assign"),
        ),
        ClauseType(
            slug="change_of_control",
            cuad_name="Change Of Control",
            question="Does a change of control trigger any rights or obligations?",
            why_it_matters="Acquisitions can trigger termination or consent requirements.",
            keywords=("change of control", "change in control", "merger", "acquisition"),
        ),
        ClauseType(
            slug="ip_ownership_assignment",
            cuad_name="Ip Ownership Assignment",
            question="Does either party assign IP ownership to the other?",
            why_it_matters="Determines who owns what gets built.",
            keywords=("intellectual property", "assign", "own", "ownership", "work product"),
        ),
        ClauseType(
            slug="audit_rights",
            cuad_name="Audit Rights",
            question="Does either party have the right to audit the other?",
            why_it_matters="Creates ongoing compliance obligations and cost.",
            keywords=("audit", "inspect", "examine", "books and records"),
        ),
        ClauseType(
            slug="insurance",
            cuad_name="Insurance",
            question="Is either party required to maintain insurance?",
            why_it_matters="A hard cost and a compliance item that is easy to miss.",
            keywords=("insurance", "insured", "coverage", "policy"),
        ),
        ClauseType(
            slug="renewal_term",
            cuad_name="Renewal Term",
            question="Does the contract renew, and how?",
            why_it_matters="Auto-renewals are a common source of unwanted spend.",
            keywords=("renew", "renewal", "automatically", "successive"),
        ),
        ClauseType(
            slug="minimum_commitment",
            cuad_name="Minimum Commitment",
            question="Is there a minimum purchase or volume commitment?",
            why_it_matters="A guaranteed spend regardless of actual need.",
            keywords=("minimum", "commit", "shall purchase", "at least"),
        ),
        ClauseType(
            slug="liquidated_damages",
            cuad_name="Liquidated Damages",
            question="Are there liquidated damages provisions?",
            why_it_matters="Pre-agreed penalties that apply without proving loss.",
            keywords=("liquidated damages", "penalty", "shall pay", "per day"),
        ),
        ClauseType(
            slug="most_favored_nation",
            cuad_name="Most Favored Nation",
            question="Is there a most-favored-nation pricing clause?",
            why_it_matters="Constrains pricing to every other customer.",
            keywords=("most favored", "most favoured", "no less favorable", "best price"),
        ),
    ]
}

BY_CUAD_NAME: dict[str, ClauseType] = {ct.cuad_name: ct for ct in CLAUSE_TYPES.values()}
