"""Eval case format.

One YAML file per contract under `evals/cases/`, each holding one case per clause type.
Cases where the clause is genuinely absent are as important as the ones where it is
present: they are how we measure refusal, which is the behaviour a law firm cares about
most. A system that invents a governing-law clause is worse than one that says "not found".
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from reviewer.interfaces import Span

CASES_DIR = Path(__file__).parent / "cases"
CONTRACTS_DIR = Path(__file__).parent / "contracts"


class ExpectedSpan(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str

    def as_span(self) -> Span:
        return Span(start=self.start, end=self.end, text=self.text)


class Expected(BaseModel):
    present: bool
    spans: list[ExpectedSpan] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Expected:
        if self.present and not self.spans:
            raise ValueError("present=true requires at least one expected span")
        if not self.present and self.spans:
            raise ValueError("present=false must not carry spans")
        return self


class Source(BaseModel):
    dataset: Literal["cuad", "synthetic", "manual"]
    id: str
    license: str = "CC-BY-4.0"


class EvalCase(BaseModel):
    id: str
    contract: str = Field(description="Filename stem under evals/contracts/")
    clause_type: str
    question: str
    expected: Expected
    source: Source
    tags: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"

    def contract_text(self, contracts_dir: Path = CONTRACTS_DIR) -> str:
        return (contracts_dir / f"{self.contract}.txt").read_text(encoding="utf-8")


class CaseFile(BaseModel):
    """A group of cases that share one contract."""

    contract: str
    title: str = ""
    cases: list[EvalCase]


def load_cases(cases_dir: Path = CASES_DIR) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.extend(CaseFile.model_validate(raw).cases)
    return cases


def validate_against_contracts(
    cases: list[EvalCase], contracts_dir: Path = CONTRACTS_DIR
) -> list[str]:
    """Return human-readable problems: missing contract files or spans that don't match."""
    problems: list[str] = []
    cache: dict[str, str] = {}
    for case in cases:
        if case.contract not in cache:
            path = contracts_dir / f"{case.contract}.txt"
            if not path.exists():
                problems.append(f"{case.id}: contract file missing: {path.name}")
                continue
            cache[case.contract] = path.read_text(encoding="utf-8")
        text = cache[case.contract]
        for span in case.expected.spans:
            actual = text[span.start : span.end]
            if actual != span.text:
                problems.append(
                    f"{case.id}: span [{span.start}:{span.end}] does not match text "
                    f"(expected {span.text[:40]!r}, found {actual[:40]!r})"
                )
    return problems
