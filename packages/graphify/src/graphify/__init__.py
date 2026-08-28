"""A knowledge graph over an indexed source tree.

Three things it is for, in the order they matter here:

1. **Tools the agent can call.** During verification the model needs to know
   what reaches a function, what a change would touch, what else lives in the
   same subsystem. Those are graph traversals, and answering them by grepping is
   guesswork with extra steps.
2. **Grouping work.** Communities say which units belong together, so a wave of
   chunks can be a coherent subsystem rather than four unrelated functions.
3. **A map to look at.** The studio draws the agent; this describes the code.

No model is involved and nothing leaves the machine. The structural half is
handed in by whoever indexed the tree; the rest is a text scan for mentions in
the files a parser skips, marked as the weaker claim it is.
"""

from .build import build, documents, is_document
from .communities import Community, detect, subsystem_of
from .export import to_html, to_json, write
from .model import Direction, Edge, KnowledgeGraph, Node, Provenance
from .query import describe_neighbours, describe_path, describe_subsystem

__all__ = [
    "Community",
    "Direction",
    "Edge",
    "KnowledgeGraph",
    "Node",
    "Provenance",
    "build",
    "describe_neighbours",
    "describe_path",
    "describe_subsystem",
    "detect",
    "documents",
    "is_document",
    "subsystem_of",
    "to_html",
    "to_json",
    "write",
]
