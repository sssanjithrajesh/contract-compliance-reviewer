### Latency and quality (this machine)

| Measure | Value | What a partner should take from it |
|---|---:|---|
| Cases | 120 | Same 120 CUAD-backed questions every run |
| p50 per question | 2383 ms | Typical look-up |
| p95 per question | 5326 ms | Slow tail; first contract pays for embedding |
| Wall time for the set | 341.8 s | Includes model load |
| Hallucinated presence | 9% | How often we invent a missing clause |
| Citation precision | 85% | Cited span overlaps expert evidence |

API token cost is $0 on `retrieval-hybrid` (local embeddings). `llm` is unmeasured until `ANTHROPIC_API_KEY` is set; then this table gains a `$ / review` row from the provider usage object.
