"""F2-A · OCPP-native static evidence extraction over a Code Property Graph.

F2-A asks the four CPG graph views (AST / CFG / DFG / CG) different questions
to assemble *reviewable evidence* that an untrusted OCPP payload field reaches a
dangerous sink without adequate checks. It does **not** confirm vulnerabilities —
its output is a candidate handed to F6.

Typical use::

    from ssat.f2a import run_f2a_file, write_artifacts
    result = run_f2a_file("result/cpg/update_firmware.c.json")
    write_artifacts(result, "result/f2a")
"""

from .graph import CPGModel
from .kb import KnowledgeBase, default_knowledge_base
from .models import EvidencePackage, F2AResult
from .pipeline import F2AAnalyzer
from .runner import run_f2a, run_f2a_file, write_artifacts

__all__ = [
    "CPGModel",
    "KnowledgeBase",
    "default_knowledge_base",
    "F2AAnalyzer",
    "F2AResult",
    "EvidencePackage",
    "run_f2a",
    "run_f2a_file",
    "write_artifacts",
]
