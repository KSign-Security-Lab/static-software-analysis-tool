"""Shared analysis knowledge: facts about the code being analysed, not about SSAT.

Two modules, answering two different questions:

- :mod:`ssat.knowledge.c_stdlib` -- what does this libc call do to memory
  (allocate, copy, read input; does it take a bound)?
- :mod:`ssat.knowledge.library_calls` -- is this call part of *any* known
  library, as opposed to user-defined?

Keep protocol- or domain-specific knowledge out of here; F2-A's OCPP knowledge
base lives in :mod:`ssat.f2a.kb`.
"""

from .c_stdlib import (
    API_SLOTS,
    BOUNDED,
    CALL_PRIORITY,
    CALL_SEM,
    CALL_SEM_ID,
    CALL_SEM_MAP,
    MEM_ALLOC_FUNCS_LOWER,
    MEM_ALLOC_FUNCS_RAW,
    STD_FUNCTIONS,
    UNBOUNDED,
    UNBOUNDED_CALLS,
    call_sem_cat_id_from_name,
)
from .library_calls import STANDARD_LIB_CALLS

__all__ = [
    "API_SLOTS",
    "BOUNDED",
    "STANDARD_LIB_CALLS",
    "CALL_PRIORITY",
    "CALL_SEM",
    "CALL_SEM_ID",
    "CALL_SEM_MAP",
    "MEM_ALLOC_FUNCS_LOWER",
    "MEM_ALLOC_FUNCS_RAW",
    "STD_FUNCTIONS",
    "UNBOUNDED",
    "UNBOUNDED_CALLS",
    "call_sem_cat_id_from_name",
]
