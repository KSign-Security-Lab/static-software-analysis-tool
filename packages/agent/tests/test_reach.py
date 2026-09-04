"""Whether a unit runs -- the second axis, and the one the reader asked for.

No model anywhere in here: `reach` is a walk over the resolved call graph, so
these are the same kind of test `test_index.py` is. If they pass, a wrong label
is a wrong *rule*; if they fail, the rule was never applied.

The bias under test is asymmetric on purpose. Calling live code `unreachable`
hides a real vulnerability behind a label a reader will trust; calling dead code
`unreferenced` costs a second's reading. So every uncertain case has to come
back weaker, not stronger.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.index import _chunk_tree, indexable
from agent.index.links import resolve_links
from agent.index.reach import compute, stamp

FIXTURE = Path(__file__).parent / "fixtures" / "reach"


def _reach(files: dict[str, str], entry_points: tuple[str, ...] = ()) -> dict[str, dict[str, object]]:
    """Reach keyed by symbol rather than chunk id, so assertions read."""
    chunks, *_ = _chunk_tree(files, indexable(files))
    computed = compute(chunks, resolve_links(chunks), entry_points)
    return {c.symbol: computed[c.chunk_id] for c in chunks if c.chunk_id in computed}


@pytest.fixture
def labelled() -> dict[str, dict[str, object]]:
    files = {
        str(path.relative_to(FIXTURE)): path.read_text(encoding="utf-8")
        for path in FIXTURE.rglob("*")
        if path.is_file()
    }
    return _reach(files)


def test_the_fixture_says_what_its_header_says(labelled) -> None:
    """The whole tree at once, against the ground truth written into it."""
    assert {symbol: entry["state"] for symbol, entry in labelled.items()} == {
        "main": "live",
        "handle_request": "live",
        "store_payload_dead": "unreachable",
        "store_payload_via_table": "unknown",
        "store_payload_exported": "unreferenced",
    }


def test_an_address_in_a_table_is_not_dead_code(labelled) -> None:
    """The trap, and the reason `unknown` exists.

    `store_payload_via_table` is static and nothing calls it by name, so every
    signal an in-degree can see says dead. Its address is in `g_handlers`, and
    `links.py` does not resolve calls through function pointers -- by design,
    it says so. Reading "no callers" as "dead" here would hide a live bug
    behind a label that invites skipping it.
    """
    assert labelled["store_payload_via_table"]["state"] == "unknown"
    assert labelled["store_payload_dead"]["state"] == "unreachable"


def test_exported_is_weaker_than_unreachable(labelled) -> None:
    """Nothing here calls it; that is not the same as nothing calling it.

    A run's tree is usually one directory of a program rather than the program,
    so a non-static function with no in-tree callers is a question, not a
    verdict.
    """
    entry = labelled["store_payload_exported"]
    assert entry["state"] == "unreferenced"
    assert entry["callers"] == 0
    assert entry["hops"] is None


def test_reached_code_records_how_far_from_an_entry_point(labelled) -> None:
    assert labelled["main"]["state"] == "live"
    assert labelled["main"]["hops"] == 0
    assert labelled["handle_request"]["hops"] == 1


def test_every_state_explains_itself_except_the_ordinary_one(labelled) -> None:
    """`why` is what lets a reader check the label instead of trusting it."""
    for symbol, entry in labelled.items():
        if entry["state"] != "live" or symbol == "main":
            assert entry["why"], f"{symbol} gives no reason for {entry['state']}"


def test_a_comment_naming_a_function_is_not_a_reference() -> None:
    """Prose mentions symbols constantly, and mentioning is not holding.

    Found by the fixture itself: its ground-truth header names every function it
    describes, which was enough to push a genuinely dead one to `unknown`.
    """
    files = {
        "a.c": (
            "/* store_payload_dead is the dead one, see also store_payload_dead. */\n"
            "// store_payload_dead again\n"
            "static void store_payload_dead(int x) { (void)x; }\n"
            "int main(void) { return 0; }\n"
        )
    }
    assert _reach(files)["store_payload_dead"]["state"] == "unreachable"


def test_a_python_underscore_is_the_language_s_own_private() -> None:
    files = {
        "m.py": (
            "def _helper():\n"
            "    return 1\n"
            "\n"
            "def public():\n"
            "    return 2\n"
        )
    }
    reach = _reach(files)
    assert reach["_helper"]["state"] == "unreachable"
    assert reach["public"]["state"] == "unreferenced"


def test_a_go_lower_case_initial_is_unexported() -> None:
    files = {
        "m.go": (
            "package main\n"
            "\n"
            "func helper() int { return 1 }\n"
            "\n"
            "func Exported() int { return 2 }\n"
        )
    }
    reach = _reach(files)
    assert reach["helper"]["state"] == "unreachable"
    assert reach["Exported"]["state"] == "unreferenced"


def test_test_and_example_paths_are_their_own_answer() -> None:
    files = {
        "tests/helper.c": "void only_used_by_tests(void) { }\n",
        "src/app.c": "void shipped(void) { }\n",
    }
    reach = _reach(files)
    assert reach["only_used_by_tests"]["state"] == "excluded"
    assert reach["shipped"]["state"] == "unreferenced"


def test_named_entry_points_override_the_call_graph() -> None:
    """A service knows what its entry points are; the call graph does not.

    Without the pattern, a handler nothing in the tree calls is `unreferenced` --
    correct and unhelpful when the framework is what calls it.
    """
    files = {"h.c": "void handle_charge(void) { }\nvoid other(void) { }\n"}

    assert _reach(files)["handle_charge"]["state"] == "unreferenced"

    named = _reach(files, entry_points=("handle_*",))
    assert named["handle_charge"]["state"] == "live"
    assert named["other"]["state"] == "unreferenced"


def test_a_caller_that_is_itself_unreachable_does_not_make_its_callee_live() -> None:
    """Reachability is transitive in the direction that matters.

    A static helper called only by another static helper that nothing calls is
    as unreached as the one above it -- and reporting it as `live` because "it
    has a caller" would be the in-degree mistake one level along.
    """
    files = {
        "a.c": (
            "static void inner(int x) { (void)x; }\n"
            "static void outer(void) { inner(1); }\n"
            "int main(void) { return 0; }\n"
        )
    }
    reach = _reach(files)
    assert reach["outer"]["state"] == "unreachable"
    assert reach["inner"]["state"] == "unreachable"
    assert reach["inner"]["callers"] == 1


def test_stamping_attaches_by_chunk_and_leaves_the_rest_alone() -> None:
    findings = [{"id": "f1", "chunk_id": "c1"}, {"id": "f2", "chunk_id": "unknown-chunk"}]
    reach = {"c1": {"state": "unreachable", "callers": 0, "hops": None, "why": []}}

    stamped = stamp(findings, reach)

    assert stamped[0]["reach"] == reach["c1"]
    # Absent rather than a default: `null` on the wire reads as "not asked",
    # and a state invented here would read as an answer.
    assert "reach" not in stamped[1]


def test_stamping_does_not_mutate_what_it_was_given() -> None:
    """The caller's list is what gets stored and cached; only the view is stamped.

    `results` is keyed by chunk id alone and replayed into later runs over other
    trees, so a reach written back into the stored payload would be one tree's
    answer served for another's.
    """
    findings = [{"id": "f1", "chunk_id": "c1"}]
    stamp(findings, {"c1": {"state": "live", "callers": 1, "hops": 1, "why": []}})

    assert findings == [{"id": "f1", "chunk_id": "c1"}]


def test_an_index_written_before_reach_existed_says_nothing() -> None:
    findings = [{"id": "f1", "chunk_id": "c1"}]
    assert stamp(findings, {}) == findings


# -- through the store, where it actually has to survive ----------------------


def test_indexing_writes_reach_beside_the_order_and_the_levels(store) -> None:
    """It is a property of the tree, so it is written once, where they are."""
    from agent.index import build_index

    files = {
        str(path.relative_to(FIXTURE)): path.read_text(encoding="utf-8")
        for path in FIXTURE.rglob("*")
        if path.is_file()
    }
    build_index(files, store)

    written = store.reach()
    by_symbol = {chunk.symbol: written.get(chunk.chunk_id) for chunk in store.chunks()}

    assert by_symbol["store_payload_dead"]["state"] == "unreachable"
    assert by_symbol["store_payload_via_table"]["state"] == "unknown"
    assert by_symbol["handle_request"]["state"] == "live"
    # File chunks are not units that can be called, so the question does not
    # apply and no answer is invented for them.
    assert by_symbol["store.c"] is None


def test_a_finding_reaches_the_report_carrying_its_reach(store) -> None:
    """The whole point, end to end: stamped on the way out, not on the way in."""
    from agent.index import build_index
    from agent.schema import Finding

    files = {
        str(path.relative_to(FIXTURE)): path.read_text(encoding="utf-8")
        for path in FIXTURE.rglob("*")
        if path.is_file()
    }
    build_index(files, store)
    dead = next(c for c in store.chunks() if c.symbol == "store_payload_dead")

    store.add_findings(
        dead.chunk_id,
        [
            {
                "schema_version": "1",
                "id": "f1",
                "chunk_id": dead.chunk_id,
                "severity": "high",
                "confidence": 0.9,
                "title": "경계 없는 복사",
                "cwe": "CWE-787",
                "primary": {
                    "file": "store.c",
                    "start_line": dead.start_line,
                    "start_column": 1,
                    "end_line": dead.start_line,
                    "end_column": 2,
                    "excerpt": "memcpy(g_slot, req->body, req->body_len);",
                },
                "explanation": "설명",
                "evidence": [],
                "remediation": {"summary": "s", "detail": "d"},
                "verified": True,
            }
        ],
    )

    stamped = stamp(store.findings(), store.reach())
    finding = Finding.model_validate(stamped[0])

    assert finding.reach is not None
    assert finding.reach.state == "unreachable"
    assert finding.reach.callers == 0
    assert finding.reach.why
    # And nothing about the finding itself moved.
    assert finding.severity == "high"
    assert finding.verified is True
