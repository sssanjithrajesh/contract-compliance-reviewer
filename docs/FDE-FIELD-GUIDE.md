# Field guide: what an FDE actually builds, why, and how we measure it

This is the study document for the portfolio. Read it as a working paper, not as
marketing. Every method below is in the repos or is the next measured change.

If you only have two hours: read sections 1, 3, 5, and 8, then the twenty sources
at the end in the order listed.

---

## 1. Why this job exists

A model in a chat box does not make a hospital, a bank, or a law firm change how
they work. Someone has to sit inside that organisation, find the real workflow,
connect the model to *their* systems, prove it does not invent facts, and leave
something the customer can run when you are gone.

That person is the forward deployed engineer. Palantir named the role. OpenAI,
Anthropic, Databricks, Scale, Glean, Harvey, and Sierra now hire it because
enterprise revenue depends on it. The job postings at $150k and above converge
on the same artefacts:

| Employer | What they say you ship | Why that artefact |
|---|---|---|
| Anthropic | MCP servers, sub-agents, agent skills | Claude only becomes useful when it can *do* things inside the customer's tools, with least privilege |
| OpenAI | Full-stack systems + eval-driven feedback that changes the product | If you cannot measure the failure, you cannot tell Research what to fix |
| Databricks | RAG, multi-agent, Text2SQL, evaluation, cloud deploy | The data already lives in a warehouse; the model has to query it without destroying it |
| Palantir | End-to-end LLM workflows on the customer's data | The question is operational ("why are flights delayed"), not academic |
| Glean (interview) | "MCP for Salesforce, Slack, and HR. Make it safe." | Connectivity without auth, scopes, and deny-by-default is a breach |

We build those artefacts in public, with numbers, because a hiring manager will
not take your word for it.

---

## 2. Why we do *this* product (contract review) first

Legal and healthcare are the verticals OpenAI staffs dedicated FDE teams for.
The failure mode is obvious to a non-engineer: if the tool invents a liability
cap that is not in the contract, a partner ships a bad mark-up. So the product
is forced to do three things every FDE system must do:

1. **Ground every claim** in a character span the user can click.
2. **Refuse** when the span is not there. "Not found" is a feature.
3. **Keep a human in the loop** before anything is marked final or written to a CRM.

That is why the demo script never says "LLM" until asked. The partner does not
buy a model. They buy a first-pass review they can defend.

A chatbot over PDFs is what everyone else ships. A scored checklist with
citations, a review queue, an outbox, and a second customer on the same binary
is what the JD describes.

---

## 3. How the core method works (retrieval, then extract, then decide)

### 3.1 The problem retrieval is solving

A commercial contract is 10–70 pages. A clause the partner cares about is often
two sentences. If you stuff the whole contract into a prompt you pay for every
token, you cannot run offline, and you still cannot *prove* where the answer
came from.

Retrieval-Augmented Generation (RAG) means: find the few passages that could
answer the question, then answer only from those. LegalBench-RAG exists because
the hard part in law is the "find" step, not the prose.

### 3.2 Why hybrid search, not vectors alone

Two signals, because they fail in different ways.

- **BM25** (Best Match 25) is lexical. It scores a passage by how often the query
  terms appear, discounted by how common those terms are in the whole document
  and by passage length. Legal drafting is formulaic ("shall be governed by the
  laws of"). BM25 is cheap and strong on boilerplate. It misses paraphrase
  ("this agreement is subject to Delaware law").
- **Dense embeddings** turn a passage into a vector so "subject to Delaware law"
  lands near "governed by the laws of Delaware." We use `BAAI/bge-small-en-v1.5`
  locally via ONNX so the air-gapped path is the same path. Dense is weaker than
  BM25 on this corpus (ADR-0002) but picks up the paraphrases BM25 drops.

**Reciprocal Rank Fusion (RRF)** merges the two ranked lists without forcing
their raw scores onto one scale (BM25 scores and cosine similarity are not
comparable). For each passage, `score = ? 1 / (k + rank)` across lists, usually
`k = 60`. Passages that are merely "okay" on both lists beat a passage that is
#1 on one list and absent on the other.

### 3.3 Why we then extract sentences

The eval does not give you points for "you found the right page." Citation
precision is: did the characters you highlighted overlap the characters a lawyer
highlighted? Citing a 1,200-character paragraph around a 40-character clause
looks like a miss. That is why the hybrid engine sat at 38% citation precision.

The method now: take the top chunks, split on sentence boundaries, keep a
sentence only if it contains a **confirm phrase** for that clause type
(`for convenience`, not just `terminate`). If retrieval liked the neighbourhood
but no sentence confirms the clause, **refuse**. That is the anti-hallucination
rule. It will raise false refusals on unusually worded clauses. We accept that
and measure it.

The LLM path (already written, not yet scored) does the same job with a model:
it may only quote verbatim substrings. A paraphrase is dropped and becomes
"not found." The model is not allowed to invent a citation.

### 3.4 Why a human still signs

Evals measure the engine. They do not absorb liability. Every finding stays
"proposed" until a named person approves or rejects it. In production the name
comes from the SSO proxy, not a text box. Writes to HubSpot or Salesforce go
through an **outbox**: the Approve click is one database transaction; delivery
to the CRM happens later with retries, jitter, and an idempotency key. A lawyer
never waits on a 429.

---

## 4. Why MCP, sub-agents, and skills

Anthropic's JD names these because they are how Claude is installed in a
customer, not how a demo is given.

- **MCP (Model Context Protocol)** is a standard for exposing tools to a model:
  list tools, call a tool, get structured results. We split servers by *trust
  boundary*: documents (read + decide), CRM (write-back), notify (Slack). A
  role that may search must not be able to write a deal. A denied call returns
  `status: denied` with a reason; it does not crash the agent.
- **Sub-agents** are narrow specialists (clause extractor, obligation checker,
  risk triage) rather than one god-prompt. Narrow tools fail in narrower ways
  and are easier to eval.
- **Skills** are the packaged instructions + tools + eval hooks you leave
  behind so the next engagement does not start from a blank context window.

The Glean interview question is the design of this layer: Salesforce + Slack +
HR, with auth, least privilege, versioning, and a story for each outage. We now
have HubSpot *and* Salesforce on the same outbox protocol. HR + Text2SQL is the
next repo, not another copy of this one.

---

## 5. What we measure, and what we compare against

We do not measure "the model is good." We measure the questions the buyer asks.

| Metric | Question it answers | How it is computed | Higher or lower |
|---|---|---|---|
| Presence accuracy | Did we correctly say the clause exists or not? | Share of cases where predicted `present` matches the label | Higher |
| Span recall | When it exists, did we find the actual text? | Share of expert spans that we covered ? 50% | Higher |
| Citation precision | When we cited something, was it real evidence? | Share of our spans that overlap any expert span | Higher |
| False refusal rate | How often did we say "not found" when it was there? | Among present cases | Lower |
| Hallucinated presence | How often did we invent a missing clause? | Among absent cases | Lower |
| p50 / p95 latency | How long does one question take? | Wall clock per case | Lower |
| $ per review | What does the API cost? | Tokens × price; $0 on the local engine | Lower |

**What we compare to**

1. **Our own keyword baseline.** A weekend script. 61% hallucination. If we
   cannot beat this, we have not earned the architecture.
2. **Our previous revision.** The gate in `evals/gate.json` is a floor. CI
   fails if a change makes the scored engine worse. The old row stays on the
   README. That is the "eval-driven feedback" OpenAI asks for.
3. **Public sets.** CUAD (Hendrycks et al., 2021): 13k+ expert spans on
   commercial contracts. LegalBench-RAG (Pipitone & Alami, 2024): the same
   idea as a retrieval benchmark with minimal gold spans. PAKTON (EMNLP 2025)
   is a published multi-agent contract reviewer; it is the yardstick, not a
   repo to clone.

We do **not** compare to "ChatGPT said the clause exists." That number is not
reproducible and does not cite offsets.

---

## 6. How we improve it (the loop, not a vibe)

This is Hamel's loop and Anthropic's eval post, applied here.

1. **Look at the failures, by clause.** The scorecard is per type. We did not
   "tune RAG." We saw `termination_for_convenience` and `ip_ownership_assignment`
   hallucinate 100% because the words "terminate" and "assign" appear everywhere.
2. **Change one thing that attacks that failure.** Confirm phrases + sentence
   citations. Not a new framework.
3. **Re-run the same 120 cases.** Promote the gate only if the metrics that
   matter moved and the ones we promised not to sacrifice (false refusal) stayed
   honest.
4. **Write the ADR.** Options, what we rejected, what it cost, what would make
   us revisit. This is the document you walk through in a decomposition round.

Next measured improvements, in order, not in parallel:

1. Score the LLM extractor on the same 120 cases. Keep it only if hallucination
   and citation precision beat retrieval-only.
2. Grow the HIPAA BAA set from 16 to ~50 and add "present but inadequate" as a
   third label.
3. Text2SQL over a warehouse schema with a golden set (Databricks JD) in a
   separate repo, with a deny-list for writes.
4. A public URL and the three-minute video. Numbers in a README that nobody can
   click are still a demo.

---

## 7. How this maps to an interview

**Decomposition (Palantir, and now everyone).** Do not start with the stack.
Start with the user (the partner), the outcome (first-pass in minutes, zero
invented clauses), the data (CUAD + the firm's PDFs), the constraint (documents
do not leave the building), the MVP (fifteen questions, cite or refuse, human
sign-off), then the failure modes (weak lexical match, CRM 429, scanned PDF).

**Client simulation.** Translate a metric into a risk: "citation precision of
38% means a third of the highlights a junior would trust are the wrong
sentence. That is why Approve is mandatory and why we changed citation to
sentences."

**MCP / integration design.** Auth per source, role per tool, outbox for writes,
idempotency keys that survive a crash, reconcile job, offline flag that fails
closed. Name what you would *not* let the model do (send mail, delete a deal,
run `DROP`).

---

## 8. What "good" looks like on a résumé for these jobs

Not "built a RAG app in LangChain." This:

> Shipped an eval-first contract reviewer: hybrid retrieval + sentence-level
> citations, human review, HubSpot/Salesforce write-back via an outbox. Cut
> hallucinated presence from 61% (keyword) to X% on 120 CUAD cases. Second
> customer (HIPAA BAA) onboarded with one YAML file.

The number is the sentence. If the number is still 24%, you are not ready to
send the link. That is why this change exists.

---

## 9. Twenty sources, in the order to read them

These are the primary texts, not blogs that restate them. Read 1–8 first.

1. [Building Effective Agents — Anthropic](https://www.anthropic.com/engineering/building-effective-agents)  
   Why most "multi-agent" systems should have been a single loop with good tools.

2. [Writing effective tools for agents — Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)  
   Tool descriptions are the interface. Small wording changes move evals.

3. [Demystifying evals for AI agents — Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)  
   You evaluate the harness + the model, not the model alone. Prefer deterministic graders.

4. [Your AI Product Needs Evals — Hamel Husain](https://hamel.dev/blog/posts/evals/)  
   Error analysis first. Domain-specific tests. The improvement loop.

5. [LLM-as-a-Judge guide — Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)  
   When a code grader is not enough, and how to validate the judge against humans.

6. [Model Context Protocol specification](https://modelcontextprotocol.io/)  
   The actual protocol Anthropic's JD is pointing at.

7. [MCP builder: how to eval a server — Anthropic skills](https://github.com/anthropics/skills/blob/main/skills/mcp-builder/reference/evaluation.md)  
   Quality of an MCP server = whether a model with *only* those tools can answer real questions.

8. [CUAD paper — Hendrycks et al., NeurIPS 2021](https://arxiv.org/abs/2103.06268)  
   The dataset our 120 cases come from. Why expert spans matter.

9. [LegalBench-RAG — Pipitone & Alami, 2024](https://arxiv.org/abs/2408.10343)  
   Retrieval, not generation, is the legal bottleneck. Minimal gold spans.

10. [ContractNLI — Koreeda & Manning, 2021](https://arxiv.org/abs/2110.01799)  
    Entailment over contracts. Useful if you add "does this clause imply X?"

11. [Reciprocal Rank Fusion — Cormack et al., SIGIR 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)  
    Why we fuse BM25 and dense by rank, not by raw score.

12. [The BM25 family — Robertson & Zaragoza](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf)  
    What the lexical half is actually doing.

13. [BGE embeddings (BAAI)](https://huggingface.co/BAAI/bge-small-en-v1.5)  
    The local model we ship in the image so offline is not a rewrite.

14. [OpenAI FDE, San Francisco](https://jobs.ashbyhq.com/openai/967f94aa-1706-4dba-ac89-bfbc2c38b688)  
    The JD: eval-driven feedback, playbooks, 5+ years, $185–300k.

15. [Anthropic FDE, Applied AI](https://job-boards.greenhouse.io/anthropic/jobs/5423029008)  
    The JD: MCP, sub-agents, skills, 4+ years.

16. [Databricks AI Engineer – FDE](https://databricks.com/company/careers/open-positions/job?gh_jid=8546367002)  
    The JD: RAG, Text2SQL, multi-agent, evals, $153–210k.

17. [Palantir Forward Deployed AI Engineer](https://jobs.lever.co/palantir/636fc05c-d348-4a06-be51-597cb9e07488)  
    The JD: workflows to production, evaluation as a basic, $135–200k.

18. [Navigating open-ended questions — Palantir](https://blog.palantir.com/navigating-open-ended-questions-65a25cd70e3d)  
    How they want you to think in the decomposition round.

19. [Reflections on Palantir — Nabeel Qureshi](https://nabeelqu.co/reflections-on-palantir)  
    What the work feels like on a real account (Airbus and after).

20. [What are Forward Deployed Engineers? — The Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/forward-deployed-engineers)  
    How OpenAI and Ramp actually run the function, with the John Deere example.

Extra, when you start Text2SQL: the [BIRD](https://bird-bench.github.io/) and
[Spider](https://yale-lily.github.io/spider) warehouse-SQL benchmarks, and
Salesforce's [REST / SOQL docs](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_what_is_rest_api.htm).

---

## 10. How to use this guide this week

- Day 1–2: sources 1, 3, 4, 8. Then read `docs/adr/0001` through `0005` in the
  contract reviewer. Notice that each ADR is the same shape as a decomposition
  answer.
- Day 3: run `uv run ccr-eval` and read `docs/scorecard.md` plus
  `docs/benchmark.md`. Pick one clause type that still fails. Write down *why*
  before touching code.
- Day 4: sources 2, 6, 7. Trace one Approve click from the UI to the outbox to
  HubSpot or Salesforce.
- Day 5: sources 14–18. Practise a 45-minute decomposition out loud on a
  different domain (invoices, tickets, 311 — you already have two of those).

Do not add a sixth repo until the flagship numbers match the demo script.
