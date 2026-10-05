# Grounded clause extraction

Used by `LLMReviewer` in `src/reviewer/pipeline.py`. The model sees only retrieved
excerpts, never the whole contract, and may only answer with verbatim quotes. Any quote
that is not a character-for-character substring of the contract is discarded by code,
and a "present" answer with no surviving quotes becomes "not found".

## System prompt

You are a contract-review assistant for a law firm. You will be given excerpts from one
contract and a question about one clause type. Decide whether the contract contains that
clause, using ONLY the excerpts. If it does, quote the exact sentence(s) that constitute
the clause, verbatim, character for character. Never paraphrase inside a quote. If the
excerpts do not contain the clause, say so. Respond with JSON only:

```json
{"present": true, "quotes": ["..."], "reasoning": "one sentence"}
```

## Why it is shaped this way

- Excerpts, not the full document: keeps cost bounded and forces the citation to come
  from something retrieval already ranked, so the eval set can score retrieval and
  extraction separately.
- Verbatim quotes, mapped back to offsets in code: the model cannot manufacture a
  citation. This is the single most important control in the system.
- One clause per call: simpler to score, simpler to cache, and a failure on one clause
  does not poison the other fourteen.

## Known failure modes

- Quotes that span a page break pick up a header or footer in the middle. The
  whitespace-tolerant matcher in `_ground` handles most; the rest fall to "not found",
  which is the safe direction.
- Clauses split across two excerpts: the model quotes one half. Span recall drops, but
  the citation is still real. Mitigation is chunk overlap (150 chars), tracked in ADR-0002.
