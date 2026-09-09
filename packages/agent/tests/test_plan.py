from __future__ import annotations

from pathlib import Path

from agent.config import AgentConfig
from agent.graph.plan import PlanEvent, PlanStore, apply_events
from agent.index import ChunkStore, build_index
from agent.runs import new_run

from conftest import read_tree

TREE = """\
#include <string.h>
#include <stdlib.h>

void helper(const char *in, char *out) {
    strcpy(out, in);
}

void middle(const char *in) {
    char buf[16];
    helper(in, buf);
}

void entry(const char *in) {
    middle(in);
}
"""


def _indexed(tmp_path: Path, name: str = "src") -> ChunkStore:
    root = tmp_path / name
    root.mkdir()
    (root / "app.c").write_text(TREE, encoding="utf-8")
    store = ChunkStore(new_run().run_id)
    build_index(read_tree(root), store)
    return store


def test_the_computed_order_seeds_the_plan(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    plan = PlanStore(store.run_id)
    plan.seed(store.order())

    assert [item.chunk_id for item in plan.items()] == store.order()
    assert {item.status for item in plan.items()} == {"pending"}
    assert [item.order_key for item in plan.items()] == list(range(len(store.order())))


def test_the_computed_traversal_is_unchanged(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    computed = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(computed)

    assert [item.chunk_id for item in plan.items()] == computed
    assert plan.pending() == computed
    assert apply_events(computed, []) == computed


def test_a_real_run_visits_the_computed_order(tmp_path: Path) -> None:
    from test_graph import ScriptedCaller

    from agent.graph.build import run_inspection

    store = _indexed(tmp_path)
    computed = store.order()
    visited: list[str] = []

    def record(event: str, payload: dict) -> None:
        if event == "chunk_started":
            visited.append(payload["chunk_id"])

    run_inspection(
        run_id="plan-order",
        files=read_tree(tmp_path / "src"),
        store=store,
        config=AgentConfig(model="fake", enable_tools=False, lenses=("injection",), lens_tools=False),
        caller=ScriptedCaller(),  # type: ignore[arg-type]
        emit=record,
    )

    assert visited == computed
    plan = PlanStore(store.run_id)
    assert [item.chunk_id for item in plan.items()] == computed
    assert plan.summary() == {"done": len(computed)}


def test_seeding_twice_does_not_forget_progress(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    plan = PlanStore(store.run_id)
    plan.seed(store.order())
    plan.mark(store.order()[:1], "done")

    plan.seed(store.order())
    assert plan.items()[0].status == "done"


def test_an_event_is_a_request_and_the_reducer_is_the_only_writer(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    plan.record([PlanEvent(kind="raise_priority", target=order[-1], reason="callers first, just this once")])

    assert plan.items()[0].chunk_id == order[-1]
    assert plan.items()[0].priority == 1
    assert plan.items()[0].order_key == len(order) - 1


def test_skip_leaves_the_queue_without_deleting_the_item(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    plan.record([PlanEvent(kind="skip", target=order[0], reason="generated code")])

    assert order[0] not in plan.pending()
    assert order[0] in [item.chunk_id for item in plan.items()]
    assert plan.summary()["skipped"] == 1


def test_the_plan_replays_exactly_from_its_event_log(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    events = [
        PlanEvent(kind="defer", target=order[0], reason="cheap, do it last"),
        PlanEvent(kind="raise_priority", target=order[-1], reason="the entry point"),
        PlanEvent(kind="skip", target=order[1], reason="a test double"),
    ]
    plan.record(events)
    stored = plan.pending()

    assert apply_events(order, plan.events()) == stored

    other = ChunkStore(new_run().run_id)
    replayed = PlanStore(other.run_id)
    replayed.seed(order)
    replayed.record(plan.events())
    assert replayed.pending() == stored


def test_an_unknown_event_kind_is_dropped_rather_than_guessed_at(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    applied = plan.record([PlanEvent(kind="reorder", target=order[0])])  # type: ignore[arg-type]

    assert applied == []
    assert plan.pending() == order
    assert plan.events() == []


def test_an_event_about_an_unknown_chunk_changes_nothing(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    plan.record([PlanEvent(kind="skip", target="not-a-chunk")])

    assert plan.pending() == order


def test_split_is_recorded_and_does_not_subdivide_anything(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    plan.record([PlanEvent(kind="split", target=order[0], reason="two concerns in one function")])

    assert plan.pending() == order
    assert "split requested" in plan.items()[0].reason
    assert [e.kind for e in plan.events()] == ["split"]


def test_advisory_is_off_by_default() -> None:
    assert AgentConfig().planning == "computed"
    assert AgentConfig().advisory_planning is False
    assert AgentConfig(planning="advisory").advisory_planning is True


def test_replan_is_absent_unless_asked_for() -> None:
    from typing import cast

    from agent.graph.build import NODES, build_graph
    from agent.graph.nodes import NodeDeps

    assert "replan" in NODES

    def shape(planning: str) -> set[str]:
        deps = NodeDeps(
            store=cast(object, None),  # type: ignore[arg-type]
            config=AgentConfig(planning=planning),
            caller=cast(object, None),  # type: ignore[arg-type]
            files={},
        )
        return set(build_graph(deps).get_graph().nodes)

    assert "replan" not in shape("computed")
    assert "replan" in shape("advisory")


def test_replan_may_only_emit_events(tmp_path: Path) -> None:
    from agent.graph.nodes import NodeDeps, make_nodes
    from agent.llm import Outcome
    from agent.schema import PlanChange, PlanRevision

    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    class Planner:
        def call(self, schema, system, user, trace=None):  # noqa: ANN001
            return Outcome.of(PlanRevision(changes=[PlanChange(kind="skip", target=order[0], reason="생성된 코드")]))

    deps = NodeDeps(
        store=store,
        config=AgentConfig(model="fake", planning="advisory"),
        caller=Planner(),  # type: ignore[arg-type]
        files={},
        plan=plan,
    )
    written = make_nodes(deps)["replan"]({"confirmed": []})  # type: ignore[arg-type]

    assert set(written) <= {"stats"}, "replan must not write traversal channels"
    assert "pending" not in written and "wave" not in written
    assert plan.summary()["skipped"] == 1


def test_a_cancelled_run_does_not_call_the_planner(tmp_path: Path) -> None:
    from agent.graph.nodes import NodeDeps, make_nodes

    store = _indexed(tmp_path)
    plan = PlanStore(store.run_id)
    plan.seed(store.order())

    class Planner:
        called = 0

        def call(self, schema, system, user, trace=None):  # noqa: ANN001
            Planner.called += 1
            raise AssertionError("the planner was asked after the run was cancelled")

    deps = NodeDeps(
        store=store,
        config=AgentConfig(model="fake", planning="advisory"),
        caller=Planner(),  # type: ignore[arg-type]
        files={},
        plan=plan,
        cancelled=lambda: True,
    )
    written = make_nodes(deps)["replan"]({"confirmed": []})  # type: ignore[arg-type]

    assert written == {}
    assert Planner.called == 0


def test_an_advisory_run_replays_from_its_event_log(tmp_path: Path) -> None:
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    plan.record(
        [
            PlanEvent(kind="raise_priority", target=order[-1], reason="entry point"),
            PlanEvent(kind="defer", target=order[0], reason="a leaf, later"),
        ]
    )
    followed = plan.pending()

    assert followed != order, "the events should have changed something"
    assert apply_events(order, plan.events()) == followed
