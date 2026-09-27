"""Sub-agents that turn raw findings into something a partner can read in two minutes.

Three narrow agents, composed by an orchestrator. Each has a rule-based path that works
offline and an LLM path that improves on it when a client is available. The rule-based
path is not a stub: it is what the air-gapped deployment ships with.

- ClauseExtractor    runs the configured reviewer over the customer's clause list
- ObligationChecker  pulls "who must do what by when" out of cited text
- RiskSummarizer     ranks findings by business impact and writes the partner summary

Nothing here may add a citation the extractor did not produce. Agents may only narrow,
rank, and explain evidence; they cannot invent it.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from reviewer.clauses import CLAUSE_TYPES
from reviewer.interfaces import Finding, Reviewer

# Clause types whose absence is itself a risk worth flagging to a partner.
ABSENCE_IS_RISK = {"cap_on_liability", "governing_law", "insurance", "anti_assignment"}
# Clause types whose presence deserves attention.
PRESENCE_IS_RISK = {
    "uncapped_liability",
    "non_compete",
    "exclusivity",
    "change_of_control",
    "liquidated_damages",
    "most_favored_nation",
    "minimum_commitment",
    "termination_for_convenience",
    "ip_ownership_assignment",
}

_OBLIGATION = re.compile(
    r"(?P<party>\b(?:[A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?"
    r"|Customer|Client|Supplier|Licensee|Licensor|Company|Contractor|CRO|Agent|Sponsor"
    r"|Distributor|Reseller|Either party|Each party)\b)"
    r"\s+(?P<verb>shall|must|will|agrees to)\s+(?P<action>[^.;]{10,160})",
)
_DEADLINE = re.compile(
    r"\b(within\s+\w+(?:\s*\(\d+\))?\s+(?:business\s+)?days?"
    r"|no later than[^.;,]{3,40}|prior to[^.;,]{3,40}|upon[^.;,]{3,40}"
    r"|annually|monthly|quarterly)\b",
    re.I,
)


@dataclass
class Obligation:
    clause_type: str
    party: str
    action: str
    deadline: str | None
    source_start: int
    source_end: int


@dataclass
class RiskItem:
    clause_type: str
    name: str
    present: bool
    severity: str  # high | medium | low
    why: str
    confidence: float
    citations: int


@dataclass
class ReviewPacket:
    findings: dict[str, Finding]
    obligations: list[Obligation]
    risks: list[RiskItem]
    summary: str
    engine: str
    used_llm: bool = False

    def as_dict(self) -> dict:
        return {
            "engine": self.engine,
            "used_llm": self.used_llm,
            "summary": self.summary,
            "risks": [asdict(r) for r in self.risks],
            "obligations": [asdict(o) for o in self.obligations],
            "findings": {k: v.model_dump() for k, v in self.findings.items()},
        }


class ClauseExtractor:
    def __init__(self, reviewer: Reviewer, clause_slugs: list[str]):
        self.reviewer = reviewer
        self.clause_slugs = clause_slugs

    def run(self, text: str) -> dict[str, Finding]:
        return {slug: self.reviewer.review(text, slug, CLAUSE_TYPES[slug].question) for slug in self.clause_slugs}


class ObligationChecker:
    def __init__(self, llm=None, model: str = "claude-sonnet-4-5"):
        self.llm = llm
        self.model = model

    def run(self, text: str, findings: dict[str, Finding]) -> list[Obligation]:
        out: list[Obligation] = []
        for slug, f in findings.items():
            if not f.present:
                continue
            for span in f.spans:
                out.extend(self._rules(slug, text, span.start, span.end))
        if self.llm is not None and out:
            out = self._refine_with_llm(text, out) or out
        # dedupe on (party, action prefix)
        seen: set[tuple[str, str]] = set()
        unique = []
        for o in out:
            key = (o.party.lower(), o.action[:60].lower())
            if key not in seen:
                seen.add(key)
                unique.append(o)
        return unique

    @staticmethod
    def _rules(slug: str, text: str, start: int, end: int) -> list[Obligation]:
        window = text[start:end]
        found = []
        for m in _OBLIGATION.finditer(window):
            action = m.group("action").strip()
            deadline = _DEADLINE.search(action)
            found.append(
                Obligation(
                    clause_type=slug,
                    party=m.group("party"),
                    action=f"{m.group('verb')} {action}",
                    deadline=deadline.group(0) if deadline else None,
                    source_start=start + m.start(),
                    source_end=start + m.end(),
                )
            )
        return found

    def _refine_with_llm(self, text: str, candidates: list[Obligation]) -> list[Obligation] | None:
        prompt = (
            "Below are candidate obligations extracted by rules from a contract, each with its source "
            "text. Remove any that are not real obligations (definitions, recitals, permissions). Normalise "
            "the party name. Keep source offsets unchanged. Return JSON: a list of objects with keys "
            "clause_type, party, action, deadline, source_start, source_end.\n\n"
            + json.dumps(
                [{**asdict(c), "source": text[c.source_start : c.source_end]} for c in candidates],
                indent=1,
            )
        )
        try:
            r = self.llm.messages.create(
                model=self.model, max_tokens=1500, messages=[{"role": "user", "content": prompt}]
            )
            raw = "".join(getattr(b, "text", "") for b in r.content)
            data = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
            valid_offsets = {(c.source_start, c.source_end) for c in candidates}
            return [
                Obligation(**{k: d.get(k) for k in Obligation.__dataclass_fields__})
                for d in data
                if (d.get("source_start"), d.get("source_end")) in valid_offsets
            ]
        except Exception:  # noqa: BLE001  - LLM refinement is best effort; rules already gave an answer
            return None


class RiskSummarizer:
    def __init__(self, llm=None, model: str = "claude-sonnet-4-5"):
        self.llm = llm
        self.model = model

    def rank(self, findings: dict[str, Finding]) -> list[RiskItem]:
        items = []
        for slug, f in findings.items():
            ct = CLAUSE_TYPES[slug]
            if f.present and slug in PRESENCE_IS_RISK:
                sev = (
                    "high"
                    if slug in {"uncapped_liability", "non_compete", "exclusivity", "change_of_control"}
                    else "medium"
                )
                why = f"Present: {ct.why_it_matters}"
            elif not f.present and slug in ABSENCE_IS_RISK:
                sev = "high" if slug == "cap_on_liability" else "medium"
                why = f"Not found: {ct.why_it_matters} Confirm this is intentional."
            elif f.present:
                sev, why = "low", f"Present and routine: {ct.why_it_matters}"
            else:
                sev, why = "low", "Not found; no action expected."
            items.append(
                RiskItem(
                    clause_type=slug,
                    name=ct.cuad_name,
                    present=f.present,
                    severity=sev,
                    why=why,
                    confidence=f.confidence,
                    citations=len(f.spans),
                )
            )
        order = {"high": 0, "medium": 1, "low": 2}
        return sorted(items, key=lambda r: (order[r.severity], -r.confidence, r.name))

    def summarize(self, contract_name: str, risks: list[RiskItem], obligations: list[Obligation]) -> str:
        high = [r for r in risks if r.severity == "high"]
        medium = [r for r in risks if r.severity == "medium"]
        lines = [f"{contract_name}: {len(high)} high-attention, {len(medium)} medium-attention items."]
        for r in high:
            lines.append(f"- HIGH  {r.name} ({'found' if r.present else 'not found'}): {r.why}")
        for r in medium[:4]:
            lines.append(f"- MED   {r.name} ({'found' if r.present else 'not found'}): {r.why}")
        dated = [o for o in obligations if o.deadline]
        if dated:
            lines.append(
                f"- {len(dated)} obligation(s) carry deadlines; first: {dated[0].party} {dated[0].action[:80]}..."
            )
        lines.append("All items are proposals pending a named lawyer's approval.")
        text = "\n".join(lines)
        if self.llm is None:
            return text
        try:
            r = self.llm.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": "Rewrite this contract-review summary for a managing partner in plain English, "
                        "keeping every fact and the final sentence exactly. Do not add findings.\n\n" + text,
                    }
                ],
            )
            return "".join(getattr(b, "text", "") for b in r.content).strip() or text
        except Exception:  # noqa: BLE001
            return text


class ReviewOrchestrator:
    def __init__(self, reviewer: Reviewer, clause_slugs: list[str], llm=None):
        self.extractor = ClauseExtractor(reviewer, clause_slugs)
        self.obligations = ObligationChecker(llm)
        self.risks = RiskSummarizer(llm)
        self.engine = getattr(reviewer, "name", "unknown")
        self.used_llm = llm is not None

    def run(self, contract_name: str, text: str) -> ReviewPacket:
        findings = self.extractor.run(text)
        obligations = self.obligations.run(text, findings)
        risks = self.risks.rank(findings)
        summary = self.risks.summarize(contract_name, risks, obligations)
        return ReviewPacket(findings, obligations, risks, summary, self.engine, self.used_llm)
