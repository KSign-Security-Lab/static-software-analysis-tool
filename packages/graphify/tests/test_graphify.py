"""The graph, the clustering, and the answers the agent's tools give back.

Everything here is deterministic and model-free, so it is tested as arithmetic
rather than sampled. The clustering in particular has to be pinned: it decides
how work is grouped, so a partition that wobbled between runs would make two
reports on one tree undiffable.
"""

from __future__ import annotations

from pathlib import Path

from graphify import (
    Edge,
    KnowledgeGraph,
    Node,
    build,
    describe_neighbours,
    describe_path,
    describe_subsystem,
    detect,
    documents,
    is_document,
    subsystem_of,
    to_html,
    to_json,
)


def _unit(name: str, file: str = "app.c") -> Node:
    return Node(id=name, kind="unit", label=name, file=file)


def _chain() -> KnowledgeGraph:
    """read -> handle -> exec, plus an unrelated pair in another file."""
    return KnowledgeGraph(
        [
            _unit("read"),
            _unit("handle"),
            _unit("exec"),
            _unit("log", "util.c"),
            _unit("fmt", "util.c"),
        ],
        [
            Edge("handle", "read", "calls"),
            Edge("handle", "exec", "calls"),
            Edge("log", "fmt", "calls"),
        ],
    )


# -- the graph ---------------------------------------------------------------


def test_an_edge_into_nothing_is_dropped() -> None:
    """A dangling edge would make a walk step into a node that is not there."""
    graph = KnowledgeGraph([_unit("a")], [Edge("a", "gone", "calls")])
    assert graph.edges == ()
    assert graph.neighbours("a") == []


def test_neighbours_come_back_nearest_first() -> None:
    graph = _chain()
    names = [n.label for n in graph.neighbours("read", hops=2)]
    assert names[0] == "handle", "one hop before two"
    assert set(names) == {"handle", "exec"}


def test_direction_separates_what_uses_from_what_is_used() -> None:
    graph = _chain()
    assert [n.label for n in graph.neighbours("handle", direction="out")] == ["read", "exec"]
    assert [n.label for n in graph.neighbours("read", direction="out")] == []
    assert [n.label for n in graph.neighbours("read", direction="in")] == ["handle"]


def test_a_path_is_found_regardless_of_which_way_the_calls_point() -> None:
    """ "How are these two related" is rarely a question about direction, and a
    directed "no path" when there is an obvious one is worse than useless."""
    graph = _chain()
    assert [n.label for n in graph.path("read", "exec")] == ["read", "handle", "exec"]
    assert graph.path("read", "log") == [], "genuinely unconnected"
    assert [n.label for n in graph.path("read", "read")] == ["read"]


def test_a_graph_survives_a_round_trip_through_json() -> None:
    graph = _chain()
    again = KnowledgeGraph.from_json(graph.to_json())
    assert set(again.nodes) == set(graph.nodes)
    assert len(again.edges) == len(graph.edges)


# -- communities -------------------------------------------------------------


def test_clustering_follows_the_calls_not_the_directories() -> None:
    graph = KnowledgeGraph(
        [_unit("a", "one.c"), _unit("b", "two.c"), _unit("c", "three.c"), _unit("x", "one.c")],
        [Edge("a", "b", "calls"), Edge("b", "c", "calls")],
    )
    communities = detect(graph)
    together = subsystem_of(communities, "a")
    assert together is not None
    assert set(together.members) == {"a", "b", "c"}, "three files, one subsystem"
    assert subsystem_of(communities, "x") is not together, "same directory, no relationship"


def test_every_node_lands_in_exactly_one_community() -> None:
    graph = _chain()
    communities = detect(graph)
    placed = [member for c in communities for member in c.members]
    assert sorted(placed) == sorted(graph.nodes)


def test_the_same_graph_always_partitions_the_same_way() -> None:
    """Not a nicety. The partition groups the work, so an unstable one means two
    runs over one tree cannot be compared."""
    graph = _chain()
    first = [(c.id, c.members) for c in detect(graph)]
    # Rebuilt with the inputs in a different order, which is the realistic way
    # for an unstable implementation to disagree with itself.
    shuffled = KnowledgeGraph(reversed(list(graph.nodes.values())), reversed(graph.edges))
    assert [(c.id, c.members) for c in detect(shuffled)] == first


def test_communities_are_numbered_largest_first() -> None:
    communities = detect(_chain())
    sizes = [len(c.members) for c in communities]
    assert sizes == sorted(sizes, reverse=True)


def test_an_empty_graph_has_no_communities() -> None:
    assert detect(KnowledgeGraph([], [])) == []


# -- documents ---------------------------------------------------------------


def test_documents_are_the_files_a_parser_skips() -> None:
    assert is_document(Path("README.md")) and is_document(Path("Makefile"))
    assert is_document(Path("config.toml")) and is_document(Path("CMakeLists.txt"))
    assert not is_document(Path("main.c")) and not is_document(Path("app.py"))


def test_a_mention_becomes_an_inferred_edge(tmp_path: Path) -> None:
    """A README naming a function is a real relationship and is not evidence of
    anything. The distinction has to survive into the graph."""
    (tmp_path / "README.md").write_text("`handle_download` fetches the firmware.", encoding="utf-8")
    nodes = [_unit("handle_download"), _unit("other")]

    doc_nodes, doc_edges = documents(nodes, tmp_path)

    assert [n.kind for n in doc_nodes] == ["doc"]
    assert [(e.dst, e.provenance) for e in doc_edges] == [("handle_download", "inferred")]


def test_short_symbols_are_not_treated_as_mentions(tmp_path: Path) -> None:
    """`id` and `fd` appear in every sentence ever written."""
    (tmp_path / "notes.md").write_text("the id of the fd is n", encoding="utf-8")
    _, edges = documents([_unit("id"), _unit("fd"), _unit("n")], tmp_path)
    assert edges == []


def test_structure_outvotes_prose_when_they_disagree(tmp_path: Path) -> None:
    """An inferred edge counts for less in the clustering, so a document that
    happens to name two unrelated functions cannot merge their subsystems."""
    (tmp_path / "README.md").write_text("about alpha_unit and beta_unit", encoding="utf-8")
    graph = build(
        [_unit("alpha_unit", "a.c"), _unit("alpha_helper", "a.c"), _unit("beta_unit", "b.c")],
        [Edge("alpha_unit", "alpha_helper", "calls")],
        root=tmp_path,
    )
    communities = detect(graph)
    alpha = subsystem_of(communities, "alpha_unit")
    assert alpha is not None and "alpha_helper" in alpha.members
    assert "beta_unit" not in alpha.members


# -- what the tools say ------------------------------------------------------


def test_a_bounded_answer_says_what_it_left_out() -> None:
    """A model told "these are the neighbours" reasons as though the list were
    complete, so a truncation that does not announce itself is a lie."""
    graph = KnowledgeGraph(
        [_unit("hub"), *(_unit(f"leaf{i:03d}") for i in range(60))],
        [Edge("hub", f"leaf{i:03d}", "calls") for i in range(60)],
    )
    answer = describe_neighbours(graph, "hub", budget=300)
    assert "not shown" in answer
    assert len(answer) < 500


def test_the_tool_answers_read_as_sentences() -> None:
    graph = _chain()
    communities = detect(graph)

    assert "handle" in describe_neighbours(graph, "read")
    assert "no such node" in describe_neighbours(graph, "nope")
    assert "3 step(s)" in describe_path(graph, "read", "exec")
    assert "no path" in describe_path(graph, "read", "log")
    assert "subsystem" in describe_subsystem(graph, communities, "read")


def test_something_connected_to_nothing_says_so() -> None:
    graph = KnowledgeGraph([_unit("alone")], [])
    assert "connected to nothing" in describe_neighbours(graph, "alone")


# -- export ------------------------------------------------------------------


def test_the_json_carries_the_counts_and_each_node_s_community() -> None:
    graph = _chain()
    payload = to_json(graph, detect(graph))

    assert payload["counts"]["nodes"] == 5
    assert payload["counts"]["communities"] == len(payload["communities"])
    assert all(node["community"] is not None for node in payload["nodes"])


def test_the_page_is_self_contained() -> None:
    """It is written beside a local run. A visualisation that needs a network
    is not a visualisation of a local run."""
    graph = _chain()
    page = to_html(graph, detect(graph), title="sample")

    assert "<script" not in page
    assert "http://" not in page and "https://" not in page
    assert "sample" in page and "handle" in page


def test_the_page_escapes_what_it_is_given() -> None:
    graph = KnowledgeGraph([Node(id="x", kind="unit", label="<script>alert(1)</script>", file="a.c")], [])
    page = to_html(graph, detect(graph))
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
