"""Contract Compliance Reviewer.

The `reviewer` package holds the system under test. Every implementation, from the
keyword baseline to the full retrieval + LLM pipeline, satisfies the same `Reviewer`
protocol so the eval harness can score any of them interchangeably.
"""

from reviewer.interfaces import Finding, Reviewer, Span

__all__ = ["Finding", "Reviewer", "Span"]
