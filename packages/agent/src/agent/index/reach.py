"""Whether a unit runs, computed from the call graph alone.

The second axis. Everything else in this package asks whether code is
*exploitable*; nothing asked whether it is *reached*, so a finding in a
never-called `static` helper and a finding in a request handler arrived in the
report looking identical and a reader worked out the difference by hand, once
per finding.

Deterministic, and no model is involved. The call graph is already resolved --
`links.resolve_links` does it at index time -- so this is a walk over data that
was being thrown away.

**It never suppresses a finding, and no model is ever shown it.** Two reasons,
and both are load-bearing. `verify` is deliberately hostile and defaults to
refuting; hand it "this is dead code" and real bugs are deleted from the report
rather than labelled -- and dead code is revived all the time. And reach is a
fact about the tree, not a claim about the code, so it belongs with the id and
the span on the server's side of `schema.py`'s line. It is attached to findings
after the fact and read by nothing that decides what to analyse.

The hard part is not `unreachable`. It is refusing to say `unreachable`:

- `links.py` leaves function pointers and macro-generated calls unresolved
  rather than guessing, so a zero in-degree can simply mean the edge was not
  resolvable.
- `MAX_AMBIGUITY` drops edges where a name has too many definitions.
- A run's tree is often a zip of one directory rather than a program, so half
  the callers may not be in the index at all.

So zero callers is never enough on its own. A unit earns `unreachable` only if
nothing in the tree calls it *and* the language says nothing outside its own
file could -- and even then, not if its name is mentioned anywhere as a value,
which is what a callback table looks like.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from fnmatch import fnmatch
from typing import Iterable, Literal, Mapping, Sequence

from ..languages import spec_for_path
from .chunk import FILE_CHUNK_KIND, Chunk
from .links import CALLS, Link

State = Literal["live", "unreferenced", "unreachable", "excluded", "unknown"]

#: Symbols that are entry points wherever they appear. Deliberately tiny: the
#: default answer for a zero-caller unit is `unreferenced`, which is already
#: honest, so this only has to name the cases where "nothing calls it" would be
#: actively misleading.
DEFAULT_ENTRY_SYMBOLS: tuple[str, ...] = ("main", "wmain", "WinMain", "_start")

#: Path fragments whose contents are not the program. Kept separate from
#: `index.SKIP_DIRS`, which decides what is *indexed* -- these are indexed and
#: analysed, they simply are not shipped code, and a finding in one is a
#: different kind of news.
EXCLUDED_PARTS: frozenset[str] = frozenset(
    {"test", "tests", "testing", "spec", "specs", "fixture", "fixtures", "mock", "mocks", "example", "examples",
     "sample", "samples", "bench", "benchmarks", "generated", "gen", "__tests__"}
)

#: Filename markers for the same thing, for trees that name rather than nest.
EXCLUDED_STEMS: tuple[str, ...] = ("test_", "_test", "_spec", ".test", ".spec", "_pb2", ".pb", "_generated")


def _is_excluded(path: str) -> bool:
    lowered = path.lower()
    parts = lowered.split("/")
    if any(part in EXCLUDED_PARTS for part in parts[:-1]):
        return True
    name = parts[-1]
    return any(marker in name for marker in EXCLUDED_STEMS)


def _declaration(chunk: Chunk) -> str:
    """Enough of the definition to see a visibility keyword on it.

    The first non-empty line, which is where `static` and `private` live in
    every grammar this indexes. Not a parse: the index holds no modifier list,
    and adding one would mean another tree-sitter pass over the whole tree to
    decide a label.
    """
    for line in chunk.body.splitlines():
        if line.strip():
            return line
    return ""


def _file_local(chunk: Chunk) -> bool:
    spec = spec_for_path(chunk.file)
    if spec is None:
        return False
    return spec.is_file_local(chunk.symbol, _declaration(chunk))


#: Block comments, and line comments in the two shapes these grammars use.
#: `#` is only a comment where it is not the preprocessor, so it is applied by
#: language rather than always -- stripping it from C would delete `#define FOO
#: handler`, which is exactly the kind of reference this is looking for.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_SLASH_COMMENT = re.compile(r"//[^\n]*")
_HASH_COMMENT = re.compile(r"#[^\n]*")
_HASH_COMMENT_LANGUAGES = frozenset({"python"})


def _code_only(chunk: Chunk) -> str:
    """The body with its comments removed.

    Prose is not a reference. The ground-truth header of a labelled fixture
    naming `store_payload_dead` was enough, without this, to make that unit
    `unknown` -- a comment about a function counted as somebody holding a
    pointer to it. Docstrings and file banners mention symbols constantly, so
    this is the ordinary case rather than a fixture artefact.
    """
    text = _BLOCK_COMMENT.sub(" ", chunk.body)
    text = _SLASH_COMMENT.sub(" ", text)
    if chunk.language in _HASH_COMMENT_LANGUAGES:
        text = _HASH_COMMENT.sub(" ", text)
    return text


def _mentioned_as_a_value(symbol: str, chunks: Sequence[Chunk], defining: str) -> bool:
    """Whether the name is used anywhere without being called.

    The guard that keeps a callback table off the `unreachable` pile. A name
    followed by `(` is a call or a declaration and tells us nothing new; a name
    that appears on its own is being passed, stored or registered, and the index
    cannot see where it ends up. That is `unknown`, and `unknown` is the answer.

    Only asked of units that would otherwise be declared unreachable, so the
    cost is one scan per genuinely orphaned symbol rather than per chunk.
    """
    pattern = re.compile(rf"\b{re.escape(symbol)}\b\s*(\()?")
    for chunk in chunks:
        if chunk.chunk_id == defining:
            continue
        for match in pattern.finditer(_code_only(chunk)):
            if match.group(1) is None:
                return True
    return False


def _entry(chunk: Chunk, patterns: Sequence[str]) -> bool:
    if chunk.symbol in DEFAULT_ENTRY_SYMBOLS:
        return True
    return any(fnmatch(chunk.symbol, pattern) for pattern in patterns)


def compute(
    chunks: Sequence[Chunk],
    links: Sequence[Link],
    entry_points: Sequence[str] = (),
) -> dict[str, dict[str, object]]:
    """Reach for every function chunk, keyed by chunk id.

    File chunks are left out. They are the file's top-level material rather than
    something that can be called, so "is it reached" is not a question about
    them -- and a finding in one is anchored to a declaration whose reachability
    is the reachability of whatever uses it.
    """
    functions = [c for c in chunks if c.kind != FILE_CHUNK_KIND]
    known = {c.chunk_id for c in functions}

    callees: dict[str, list[str]] = defaultdict(list)
    callers: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link.kind == CALLS and link.src in known and link.dst in known and link.src != link.dst:
            callees[link.src].append(link.dst)
            callers[link.dst].append(link.src)

    local = {c.chunk_id: _file_local(c) for c in functions}
    excluded = {c.chunk_id: _is_excluded(c.file) for c in functions}

    # Two kinds of root, and the difference is the whole reason this is useful.
    #
    # An *entry* is something the operator named or the language declares --
    # `main`, a handler pattern. It is live by definition.
    #
    # A *candidate* is a unit nothing in the tree calls but something outside it
    # could: an exported function, in a tree that is usually one directory of a
    # program rather than the program. It has to seed the walk, or a library's
    # entire call graph reads as dead -- but it is not itself evidence that
    # anything runs, so it keeps the weaker label. Saying `live` there would be
    # asserting the very thing the index cannot see.
    entries = {c.chunk_id for c in functions if _entry(c, entry_points)}
    candidates = {
        c.chunk_id
        for c in functions
        if not callers[c.chunk_id] and not local[c.chunk_id] and not excluded[c.chunk_id]
    }

    hops: dict[str, int] = {}
    queue: deque[str] = deque()
    for root in [*entries, *candidates]:
        if root not in hops:
            hops[root] = 0
            queue.append(root)
    while queue:
        node = queue.popleft()
        for callee in callees[node]:
            if callee not in hops:
                hops[callee] = hops[node] + 1
                queue.append(callee)

    out: dict[str, dict[str, object]] = {}
    for chunk in functions:
        chunk_id = chunk.chunk_id
        count = len(set(callers[chunk_id]))
        why: list[str] = []
        state: State

        if excluded[chunk_id]:
            state = "excluded"
            why.append("시험·예제·생성 코드 경로")
        elif chunk_id in entries:
            state = "live"
            why.append("진입점")
        elif hops.get(chunk_id):
            # Strictly greater than zero: something in the tree actually calls
            # it. A candidate root sits at zero and has not earned this.
            state = "live"
        elif chunk_id in candidates:
            state = "unreferenced"
            why.append("트리 안에 호출자 없음")
            why.append("파일 밖에서는 부를 수 있음")
        elif count:
            # Called, but only by things that are not themselves reached. The
            # honest answer is that its callers decide, and they are not live.
            state = "unreachable"
            why.append("호출자가 모두 도달 불가")
        elif local[chunk_id]:
            if _mentioned_as_a_value(chunk.symbol, chunks, chunk_id):
                state = "unknown"
                why.append("이름이 값으로 쓰인 곳이 있음 (콜백 테이블일 수 있음)")
            else:
                state = "unreachable"
                why.append("파일 밖에서 부를 수 없는 선언")
                why.append("트리 안에 호출자 없음")
        else:
            state = "unreferenced"
            why.append("트리 안에 호출자 없음")
            why.append("파일 밖에서는 부를 수 있음")

        out[chunk_id] = {
            "state": state,
            "callers": count,
            # Only for something actually reached. A candidate root sits at zero
            # in the walk because it seeded it, and reporting that as "zero hops
            # from an entry point" would dress the assumption up as a finding.
            "hops": hops.get(chunk_id) if state == "live" else None,
            "why": why,
        }

    return out


def stamp(findings: Iterable[dict[str, object]], reach: Mapping[str, dict[str, object]]) -> list[dict[str, object]]:
    """Attach reach to findings, by the chunk each was found in.

    Stamped rather than stored. `cache.recall` replays finding payloads produced
    by an earlier run over a *different* tree, so a reach baked into the payload
    would be one tree's answer served for another's. Read from the run's own
    index every time it is shown instead, which costs nothing and cannot be
    stale.

    A chunk with no entry -- a file chunk, or an index written before this
    existed -- leaves the field absent, which is `null` on the wire and reads as
    "not asked" rather than as an answer.
    """
    out: list[dict[str, object]] = []
    for finding in findings:
        found = reach.get(str(finding.get("chunk_id", "")))
        out.append({**finding, "reach": found} if found else dict(finding))
    return out
