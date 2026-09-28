"""Build the manually annotated healthcare (BAA) eval cases.

    uv run python -m scripts.build_baa_evals

CUAD does not cover HIPAA Business Associate Agreements, so these cases are annotated by
hand: each anchor below is the exact sentence (or sentence start) that constitutes the
clause. Offsets are computed from the anchor so the case can never drift from the text.
An anchor of None means the clause is genuinely absent, which is the point of the
deficient vendor addendum: it reads like a BAA and is missing five required elements.

Source texts:
- hhs-sample-baa.txt        modelled on HHS's published sample BAA provisions (public domain)
- vendor-baa-deficient.txt  a realistic vendor "data protection addendum" that is not a valid BAA
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "evals" / "cases"
CONTRACTS_DIR = ROOT / "evals" / "contracts"

# clause slug -> list of anchor strings (exact substrings) or None for absent
ANNOTATIONS: dict[str, dict[str, list[str] | None]] = {
    "hhs-sample-baa": {
        "baa_permitted_uses": [
            "Business Associate agrees to not use or disclose Protected Health Information other than as permitted or required by this Agreement or as required by law.",
            "Business Associate may only use or disclose Protected Health Information as necessary to perform the billing and claims processing services set forth in the Master Services Agreement.",
        ],
        "baa_safeguards": [
            "Business Associate agrees to use appropriate administrative, physical, and technical safeguards, and comply with Subpart C of 45 CFR Part 164 with respect to electronic Protected Health Information, to prevent use or disclosure of Protected Health Information other than as provided for by this Agreement.",
        ],
        "baa_breach_notification": [
            "Business Associate agrees to report to Covered Entity any use or disclosure of Protected Health Information not provided for by this Agreement of which it becomes aware, including breaches of unsecured Protected Health Information as required at 45 CFR 164.410, and any security incident of which it becomes aware. Such report shall be made without unreasonable delay and in no case later than ten (10) business days after discovery.",
        ],
        "baa_subcontractors": [
            "Business Associate agrees to ensure that any subcontractors that create, receive, maintain, or transmit Protected Health Information on behalf of Business Associate agree in writing to the same restrictions, conditions, and requirements that apply to Business Associate with respect to such information.",
        ],
        "baa_individual_rights": [
            "Business Associate agrees to make available Protected Health Information in a designated record set to Covered Entity as necessary to satisfy Covered Entity's obligations under 45 CFR 164.524, within fifteen (15) business days of a request.",
            "Business Associate agrees to make any amendment(s) to Protected Health Information in a designated record set as directed or agreed to by Covered Entity pursuant to 45 CFR 164.526",
            "Business Associate agrees to maintain and make available the information required to provide an accounting of disclosures to Covered Entity as necessary to satisfy Covered Entity's obligations under 45 CFR 164.528.",
        ],
        "baa_hhs_access": [
            "Business Associate agrees to make its internal practices, books, and records available to the Secretary of the Department of Health and Human Services for purposes of determining compliance with the HIPAA Rules.",
        ],
        "baa_return_destroy": [
            "(b) return to Covered Entity or, if agreed to by Covered Entity, destroy the remaining Protected Health Information that Business Associate still maintains in any form;",
            "If return or destruction is infeasible, Business Associate shall notify Covered Entity of the conditions that make return or destruction infeasible and shall extend the protections of this Agreement to such Protected Health Information and limit further uses and disclosures to those purposes that make the return or destruction infeasible.",
        ],
        "baa_termination_for_breach": [
            "Business Associate authorizes termination of this Agreement by Covered Entity, if Covered Entity determines Business Associate has violated a material term of the Agreement and Business Associate has not cured the breach or ended the violation within thirty (30) days of written notice of the breach.",
        ],
    },
    "vendor-baa-deficient": {
        "baa_permitted_uses": [
            "Vendor shall treat all Customer Data, including any protected health information, as confidential and shall use Customer Data solely to provide the Services described in the Subscription Agreement and for no other purpose.",
        ],
        "baa_safeguards": [
            "Vendor maintains an information security program that includes administrative, physical, and technical safeguards designed to protect the confidentiality, integrity, and availability of Customer Data, consistent with industry standards and the HIPAA Security Rule at 45 CFR Part 164 Subpart C.",
        ],
        # Present but weak: "confirmed unauthorized access", no deadline. Still a reporting clause.
        "baa_breach_notification": [
            "Vendor shall notify Customer of any confirmed unauthorized access to Customer Data. Vendor will provide such notice as soon as reasonably practicable after Vendor completes its internal investigation.",
        ],
        "baa_subcontractors": None,
        "baa_individual_rights": None,
        "baa_hhs_access": None,
        "baa_return_destroy": None,  # "export your data before termination" is not return-or-destroy
        "baa_termination_for_breach": None,
    },
}

QUESTIONS = {
    "baa_permitted_uses": "Does the agreement limit how the business associate may use or disclose protected health information?",
    "baa_safeguards": "Must the business associate implement administrative, physical, and technical safeguards?",
    "baa_breach_notification": "Must the business associate report breaches or security incidents, and within what time?",
    "baa_subcontractors": "Must subcontractors agree to the same restrictions in writing?",
    "baa_individual_rights": "Does the business associate have to support access, amendment, and accounting-of-disclosures requests?",
    "baa_hhs_access": "Must the business associate make its practices, books, and records available to HHS?",
    "baa_return_destroy": "At termination, must PHI be returned or destroyed, and what happens if that is infeasible?",
    "baa_termination_for_breach": "May the covered entity terminate if the business associate violates a material term?",
}


def main() -> int:
    total = present = 0
    for contract, clauses in ANNOTATIONS.items():
        text = (CONTRACTS_DIR / f"{contract}.txt").read_text(encoding="utf-8")
        cases = []
        for slug, anchors in clauses.items():
            spans = []
            if anchors:
                for anchor in anchors:
                    start = text.find(anchor)
                    if start < 0:
                        raise SystemExit(f"{contract}/{slug}: anchor not found: {anchor[:60]!r}")
                    spans.append({"start": start, "end": start + len(anchor), "text": anchor})
            is_present = bool(spans)
            cases.append(
                {
                    "id": f"{contract}__{slug}",
                    "contract": contract,
                    "clause_type": slug,
                    "question": QUESTIONS[slug],
                    "expected": {"present": is_present, "spans": spans},
                    "source": {"dataset": "manual", "id": f"{contract}:{slug}", "license": "public-domain"},
                    "tags": (["present"] if is_present else ["absent", "refusal"]) + ["healthcare", "baa"],
                    "difficulty": "hard" if len(spans) > 1 else "medium",
                }
            )
            total += 1
            present += is_present
        payload = {"contract": contract, "title": f"{contract} (manual BAA annotation)", "cases": cases}
        (CASES_DIR / f"manual-{contract}.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
        )
        print(f"  {contract}: {len(cases)} cases")
    print(f"\nwrote {total} healthcare cases ({present} present / {total - present} absent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
