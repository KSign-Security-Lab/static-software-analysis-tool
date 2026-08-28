"""Local tracing: record the call tree of an inspection in the run's own store."""

from .recorder import SpanRecorder
from .store import Span, SpanStore

__all__ = ["Span", "SpanRecorder", "SpanStore"]
