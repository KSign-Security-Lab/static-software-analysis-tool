"""The SEC-bench sweep: fetch, run, score.

Offline by construction -- nothing here is imported by the graph or the API's
inspect path. A benchmark you can trigger from a request is a benchmark you will
iterate against, and the moment we tune against a held-out set it stops
measuring us and starts measuring how often we looked.
"""

from .config import BenchConfig
from .dataset import Instance, fetch, load, select

__all__ = ["BenchConfig", "Instance", "fetch", "load", "select"]
