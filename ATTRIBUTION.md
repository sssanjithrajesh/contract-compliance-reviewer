# Attribution

## CUAD (Contract Understanding Atticus Dataset)

The contract texts in `evals/contracts/` and the clause annotations in `evals/cases/`
are derived from CUAD v1, created by The Atticus Project and released under the
Creative Commons Attribution 4.0 International licence (CC-BY 4.0).

- Dataset: https://www.atticusprojectai.org/cuad
- Code and data: https://github.com/TheAtticusProject/cuad
- Paper: Hendrycks, Burns, Chen, Ball. "CUAD: An Expert-Annotated NLP Dataset for Legal
  Contract Review." NeurIPS 2021 Datasets and Benchmarks. https://arxiv.org/abs/2103.06268

Changes made: a deterministic sample of 8 of the 102 test-split contracts was taken;
15 of the 41 clause categories were kept and renamed to internal slugs; annotations
were reformatted into the YAML schema in `evals/schema.py`. No contract text was altered.

The original contracts are public filings with the US Securities and Exchange Commission.

## Code

Everything else in this repository is MIT licensed. See `LICENSE`.
