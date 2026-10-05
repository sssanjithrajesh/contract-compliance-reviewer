"""Build the eval set from the public CUAD dataset.

    uv run ccr-build-evals                # download if needed, sample, write cases
    uv run ccr-build-evals --contracts 8  # change sample size

What it does:
1. Downloads CUAD's SQuAD-format `data.zip` (CC-BY 4.0, Atticus Project) into data/raw/.
2. Picks N contracts deterministically (seeded) from the held-out test split, preferring
   ones short enough to commit and with a healthy mix of present/absent clauses.
3. For each of our 15 clause types, writes one case: present with the annotated spans,
   or absent (CUAD marks these `is_impossible`).
4. Writes contract text to evals/contracts/ and cases to evals/cases/.

Spans are verified against the text before writing, so a case can never drift from the
contract it points at.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import urllib.request
import zipfile
from pathlib import Path

import yaml

from reviewer.clauses import BY_CUAD_NAME

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CASES_DIR = ROOT / "evals" / "cases"
CONTRACTS_DIR = ROOT / "evals" / "contracts"
CUAD_URL = "https://github.com/TheAtticusProject/cuad/raw/main/data.zip"
SEED = 20260926
MAX_CONTRACT_CHARS = 70_000
MIN_PRESENT_FRACTION = 0.35


def ensure_data() -> Path:
    test_json = RAW_DIR / "test.json"
    if test_json.exists():
        return test_json
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "cuad_data.zip"
    print(f"downloading {CUAD_URL} ...")
    urllib.request.urlretrieve(CUAD_URL, zip_path)  # noqa: S310 (fixed trusted URL)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(RAW_DIR)
    return test_json


def agreement_kind(title: str) -> str:
    """Pull the human agreement type out of CUAD's three title formats.

    "Loha..._EX-10.16_Supply Agreement"           -> "supply agreement"
    "CENTRACK..._10_29_1999-EX-10.3-WEB SITE HOSTING AGREEMENT" -> "web site hosting agreement"
    "PACIRA ... - A_R STRATEGIC LICENSING, ... AGREEMENT" -> "strategic licensing ... agreement"
    """
    tail = re.split(r"EX-[\d.]+(?:\([A-Z]+\))?[-_ ]+", title, flags=re.I)[-1]
    tail = tail.rsplit(" - ", 1)[-1]
    tail = re.sub(r"^A_R\s+", "", tail)
    return re.sub(r"\s+", " ", tail.strip().lower())


def slugify(title: str) -> str:
    company = re.split(r"[_,\s-]", title.strip())[0]
    slug = re.sub(r"[^a-z0-9]+", "-", f"{company}-{agreement_kind(title)}".lower()).strip("-")
    return slug[:60]


def contract_cases(entry: dict) -> tuple[str, list[dict]]:
    """Return (context, cases) for one CUAD contract, restricted to our clause types."""
    paragraph = entry["paragraphs"][0]
    context: str = paragraph["context"]
    slug = slugify(entry["title"])
    cases = []
    for qa in paragraph["qas"]:
        cuad_name = qa["id"].split("__")[-1]
        ct = BY_CUAD_NAME.get(cuad_name)
        if ct is None:
            continue
        present = not qa.get("is_impossible", False) and bool(qa["answers"])
        spans = []
        seen: set[tuple[int, int]] = set()
        for ans in qa["answers"]:
            start = ans["answer_start"]
            end = start + len(ans["text"])
            if context[start:end] != ans["text"]:
                continue  # skip mis-aligned annotations rather than commit a broken case
            if (start, end) in seen:
                continue
            seen.add((start, end))
            spans.append({"start": start, "end": end, "text": ans["text"]})
        if present and not spans:
            continue
        cases.append(
            {
                "id": f"{slug}__{ct.slug}",
                "contract": slug,
                "clause_type": ct.slug,
                "question": ct.question,
                "expected": {"present": present, "spans": spans if present else []},
                "source": {"dataset": "cuad", "id": qa["id"], "license": "CC-BY-4.0"},
                "tags": ["present"] if present else ["absent", "refusal"],
                "difficulty": "hard" if present and len(spans) > 2 else "medium",
            }
        )
    return context, cases


def pick_contracts(data: list[dict], n: int, rng: random.Random) -> list[dict]:
    eligible = []
    for entry in data:
        context, cases = contract_cases(entry)
        if not cases or len(context) > MAX_CONTRACT_CHARS:
            continue
        present_frac = sum(c["expected"]["present"] for c in cases) / len(cases)
        if present_frac < MIN_PRESENT_FRACTION:
            continue
        eligible.append(entry)
    rng.shuffle(eligible)

    # Round-robin across agreement kinds so the set is not eight endorsement deals.
    by_kind: dict[str, list[dict]] = {}
    for entry in eligible:
        by_kind.setdefault(agreement_kind(entry["title"]), []).append(entry)
    chosen: list[dict] = []
    while len(chosen) < n and any(by_kind.values()):
        for kind in sorted(by_kind):
            if by_kind[kind] and len(chosen) < n:
                chosen.append(by_kind[kind].pop())
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contracts", type=int, default=8)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    test_json = ensure_data()
    data = json.loads(test_json.read_text(encoding="utf-8"))["data"]
    rng = random.Random(args.seed)
    chosen = pick_contracts(data, args.contracts, rng)

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    for old in list(CASES_DIR.glob("*.yaml")) + list(CONTRACTS_DIR.glob("*.txt")):
        old.unlink()

    total = present = 0
    for entry in chosen:
        context, cases = contract_cases(entry)
        slug = cases[0]["contract"]
        (CONTRACTS_DIR / f"{slug}.txt").write_text(context, encoding="utf-8", newline="\n")
        payload = {"contract": slug, "title": entry["title"], "cases": cases}
        (CASES_DIR / f"{slug}.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        total += len(cases)
        present += sum(c["expected"]["present"] for c in cases)
        print(f"  {slug}: {len(cases)} cases ({len(context):,} chars)")

    print(f"\nwrote {total} cases across {len(chosen)} contracts ({present} present / {total - present} absent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
