# Post-mortem: intermittent CI failure in Slack signature verification test

Severity: low (CI only, no customer impact). Time to detect: 1 CI run. Time to fix: ~20 min.
Written because a flaky security test is worse than no test: it trains people to re-run CI
instead of reading it.

## What happened

`tests/test_integrations.py::test_slack_signature_rejects_tampering` failed on roughly one
CI run in sixteen, always with the same assertion: a tampered signature was *accepted*.
Locally it passed every time it was run by hand.

## Timeline

- Phase 3 PR opened; first CI run green.
- Rebase and re-push for an unrelated ruff fix; CI red on the signature test only.
- Re-run: green. Re-run of the same commit: green. Third re-run: red.
- Investigation started once it failed on an identical commit, which rules out the diff.

## Root cause

The test built a tampered signature by replacing the last hex character:

```python
tampered = sig[:-1] + "0"
```

One hex digit in sixteen is already `"0"`. On those runs the "tampered" signature was
byte-identical to the real one, the verifier correctly accepted it, and the assertion that
it should be rejected failed. The verifier was never wrong; the test was wrong 6.25% of
the time, and only when the HMAC of that run's timestamp happened to end in zero.

## Fix

```python
tampered = sig[:-1] + ("1" if sig[-1] == "0" else "0")
```

Guaranteed to differ from the original. One line.

## Why it took three CI runs to look

Because "flaky test, re-run" is the default reflex, and the failure rate was low enough
that two re-runs in a row could pass. The signal that finally triggered investigation was
the failure reproducing on an unchanged commit.

## What we changed beyond the fix

1. **Rule for the repo:** a test that fails on an unchanged commit is a bug, not noise. It
   gets investigated before the next re-run, not after.
2. **Rule for security tests specifically:** negative cases (bad signature, bad token,
   missing header) must construct their bad input so that it is *provably* different from
   the good input, not probably different. Random-looking data is not the same as
   different data.
3. Added the same check to the `verify_signature` docstring so the next person writing a
   test against it sees the pitfall.

## What we did not change

We did not add a retry-on-failure to CI. Retries would have hidden this permanently, and
the next time this pattern appears it might be in the verifier rather than the test.

## Lessons for the engagement

The customer asked "will it get worse after an update?" and the answer is the CI gate.
That answer is only as good as the discipline around red builds. A one-in-sixteen flake
would have eroded that discipline within a month.
