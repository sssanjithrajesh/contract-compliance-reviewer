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
    # Phrases that must appear in a cited sentence. Broader `keywords` still help
    # retrieval; these are the anti-hallucination check. Empty means "use keywords".
    confirm: tuple[str, ...] = field(default_factory=tuple)

    def confirm_phrases(self) -> tuple[str, ...]:
        return self.confirm or self.keywords


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
            confirm=("for convenience", "without cause", "for any reason", "without reason", "no cause"),
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
            confirm=("limitation of liability", "shall not exceed", "liability cap", "aggregate liability", "in no event"),
        ),
        ClauseType(
            slug="uncapped_liability",
            cuad_name="Uncapped Liability",
            question="Are there carve-outs where liability is uncapped?",
            why_it_matters="Carve-outs (fraud, IP, confidentiality) are the real exposure.",
            keywords=("shall not apply to", "except", "gross negligence", "willful misconduct"),
            confirm=("shall not apply", "gross negligence", "willful misconduct", "unlimited liability", "without limitation of liability"),
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
            confirm=("change of control", "change in control"),
        ),
        ClauseType(
            slug="ip_ownership_assignment",
            cuad_name="Ip Ownership Assignment",
            question="Does either party assign IP ownership to the other?",
            why_it_matters="Determines who owns what gets built.",
            keywords=("intellectual property", "assign", "own", "ownership", "work product"),
            confirm=("intellectual property", "work product", "hereby assigns", "assigns all", "ip ownership"),
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
            confirm=(
                "minimum purchase",
                "minimum commitment",
                "minimum volume",
                "minimum quantities",
                "minimum quantity",
                "shall purchase at least",
                "minimum order",
            ),
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
            confirm=("most favored", "most favoured", "no less favorable", "most favoured nation", "most favored nation"),
        ),
        # --- Healthcare: HIPAA Business Associate Agreement checklist (45 CFR 164.504(e)) ---
        # `cuad_name` doubles as the display name; these are not in CUAD and are evaluated on
        # manually annotated cases (evals/cases/manual-*.yaml).
        ClauseType(
            slug="baa_permitted_uses",
            cuad_name="Permitted Uses and Disclosures of PHI",
            question=(
                "Does the agreement limit how the business associate may use or disclose protected health information?"
            ),
            why_it_matters="Required by 164.504(e)(2)(i); without it the agreement is not a valid BAA.",
            keywords=("permitted uses", "use or disclose", "protected health information", "PHI", "only as permitted"),
        ),
        ClauseType(
            slug="baa_safeguards",
            cuad_name="Safeguards",
            question="Must the business associate implement administrative, physical, and technical safeguards?",
            why_it_matters="Required; ties the vendor to the Security Rule.",
            keywords=("safeguards", "administrative, physical", "technical safeguards", "security rule"),
        ),
        ClauseType(
            slug="baa_breach_notification",
            cuad_name="Breach and Incident Reporting",
            question="Must the business associate report breaches or security incidents, and within what time?",
            why_it_matters="Drives the covered entity's own 60-day notification clock.",
            keywords=("breach", "security incident", "report", "notify", "unsecured protected health information"),
        ),
        ClauseType(
            slug="baa_subcontractors",
            cuad_name="Subcontractor Flow-Down",
            question="Must subcontractors agree to the same restrictions in writing?",
            why_it_matters="Required by 164.502(e)(1)(ii); the most commonly missing clause.",
            keywords=("subcontractor", "agents", "same restrictions", "flow down", "written agreement"),
        ),
        ClauseType(
            slug="baa_individual_rights",
            cuad_name="Individual Access, Amendment, and Accounting",
            question=(
                "Does the business associate have to support access, amendment, and accounting-of-disclosures requests?"
            ),
            why_it_matters="Required for designated record sets; a frequent operational gap.",
            keywords=("access", "amendment", "accounting of disclosures", "designated record set", "164.524"),
        ),
        ClauseType(
            slug="baa_hhs_access",
            cuad_name="HHS Access to Books and Records",
            question="Must the business associate make its practices, books, and records available to HHS?",
            why_it_matters="Required by 164.504(e)(2)(ii)(I).",
            keywords=("Secretary", "HHS", "books and records", "internal practices", "available to"),
        ),
        ClauseType(
            slug="baa_return_destroy",
            cuad_name="Return or Destruction of PHI at Termination",
            question="At termination, must PHI be returned or destroyed, and what happens if that is infeasible?",
            why_it_matters="Required; determines the vendor's post-contract data footprint.",
            keywords=("return or destroy", "termination", "infeasible", "retain", "destruction"),
        ),
        ClauseType(
            slug="baa_termination_for_breach",
            cuad_name="Termination for Material Breach",
            question="May the covered entity terminate if the business associate violates a material term?",
            why_it_matters="Required by 164.504(e)(2)(iii).",
            keywords=("material breach", "terminate", "cure", "violated a material term"),
        ),
    ]
}

BY_CUAD_NAME: dict[str, ClauseType] = {ct.cuad_name: ct for ct in CLAUSE_TYPES.values()}
