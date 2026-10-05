# Three-minute demo script

Audience: a practice-group partner and the firm's IT lead. Goal: they leave knowing three
things: it does not make things up, a human signs every decision, and it runs inside
their walls. Do not show code. Do not say "LLM" until asked.

Setup before they arrive (one terminal, one browser tab, everything offline):

```
set CCR_OFFLINE=1
uv run ccr-serve
```

Have two files on the desktop: `msa-complete.txt` (a full master services agreement from
the eval set) and `vendor-baa-deficient.txt`.

---

**0:00 - The problem, in their words** (20 s)

"You told us associates spend three to four hours on first-pass review of a vendor
contract, and the thing you worry about is not speed, it is confidence: did they miss a
clause, and can you trust what the tool says. So here is what we built to answer that
second question first."

**0:20 - Upload a complete contract** (40 s)

Drag `msa-complete.txt` into the upload box. The review page loads in a few seconds.

Point at one finding, say Governing Law. "Every claim is a quote from the contract, with
the page and the character offsets. Click it. That is the exact text. If the tool cannot
point at text, it is not allowed to say the clause exists."

Point at one marked "not found". "Same rule in reverse. This is a 'not found' with no
quote, because there is nothing to quote. It did not guess."

**1:00 - The approval, and why the name matters** (30 s)

Click Approve on Governing Law. In the pilot, type a name; in production, show the SSO
name already filled from the login.

"Nothing leaves this screen until a person with a name approves it. That name and
timestamp go to the matter record and the audit export. This is the point where your
professional judgement enters, and it is the only path to the CRM."

**1:30 - The deficient contract** (45 s)

Upload `vendor-baa-deficient.txt`. "This one looks like a proper agreement. It has
confidentiality, security, a breach clause." Scroll. "Five required elements are simply
not in it, and the tool says so, with no invented quotes. A first-year associate reading
quickly would very likely miss that the return-or-destroy obligation is missing, because
there is an export clause that sounds close."

This is the moment. Let it sit for a beat.

**2:15 - How we know it will stay this good** (30 s)

Open `docs/scorecard.svg` in the browser. "Before writing the tool we wrote the exam: 120
questions drawn from expert-annotated public contracts, half of them about clauses that
are absent. Every change we ship is graded against it, and a change that scores lower
cannot be merged. The number you care about is this one: how often it claims a clause
that is not there. Sixty-one percent for the keyword approach lawyers usually get shown.
This version is at twenty-four on your contract types and zero on the healthcare set, and
the next iteration with the extraction model is graded against the same exam before you
see it."

**2:45 - Where it runs** (15 s)

"Everything you just saw ran with the network off. The model that reads the contract is
inside the container. When you want the stronger extraction model, that is one switch
and a key, and your IT team decides when."

**3:00 - Stop talking.**

---

## Questions they will ask, and the answers

**"What does it get wrong?"** Short contracts and contracts that describe a clause without
using any of the usual words. It says "not found" in those cases rather than guessing;
we would rather you check a false negative than trust a false positive. The scorecard
shows the false-refusal rate is 9%.

**"Can it draft the redline?"** Not today, on purpose. Extraction we can grade; drafting
we cannot yet, so we did not ship it.

**"Who else uses this?"** A healthcare client uses the same software for HIPAA business
associate agreements. Different clauses, different rules, same code, one config file.
That is why we can support you at a reasonable price.

**"What happens if HubSpot is down?"** Approvals are queued and delivered when it is back,
exactly once. Nothing is lost and nothing is duplicated.

**"Does our data leave the building?"** Not in the configuration you just saw. If you
enable the external model, contract text goes to the model provider under their
zero-retention terms, and the audit log records which reviews used it.
