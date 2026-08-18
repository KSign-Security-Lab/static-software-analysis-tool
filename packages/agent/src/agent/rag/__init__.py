"""Retrieval over things that are not this run's code.

The run's own index answers "where in this code"; that lives in `agent/index/`.
This answers "what is this code like", against a corpus of known weaknesses
recorded before the run existed and outliving it.
"""

from .corpus import FIXED, VULNERABLE, Sample, Unavailable, counts, ingest, read, search

__all__ = ["FIXED", "VULNERABLE", "Sample", "Unavailable", "counts", "ingest", "read", "search"]
