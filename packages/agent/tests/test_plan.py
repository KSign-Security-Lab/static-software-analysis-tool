"""The plan: recorded, foldable, and unable to move the run.

The load-bearing test is `test_the_computed_traversal_is_unchanged`. Everything
else here is about the plan being useful; that one is about it being safe, and
it is the one that fails if the plan ever becomes something the graph reads.
"""

from __future__ import annotations

from pathlib import Path

from agent.config import AgentConfig
from agent.graph.plan import PlanEvent, PlanStore, apply_events
from agent.index import ChunkStore, build_index
from agent.runs import new_run

from conftest import read_tree

# Three functions in a call chain plus a file chunk, so the computed order has
# something to be an order *of*: `helper` before `middle` before `entry`.
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
    """The invariant `graph/build.py` states, asserted rather than assumed.

    An untouched plan has every priority at zero, so ordering by
    (-priority, order_key) collapses to the order key -- the order the index
    wrote. Byte-identical, not merely equivalent: this compares the sequences,
    not their contents.

    It is written against the fold rather than against a live run on purpose. A
    run would prove the same thing more slowly and only for the one tree it
    happened to walk; the fold is where the property actually lives, so this is
    the layer that can be wrong.
    """
    store = _indexed(tmp_path)
    computed = store.order()

    plan = PlanStore(store.run_id)
    plan.seed(computed)

    assert [item.chunk_id for item in plan.items()] == computed
    assert plan.pending() == computed
    # And the in-memory fold agrees with the stored one, with no events.
    assert apply_events(computed, []) == computed


def test_a_real_run_visits_the_computed_order(tmp_path: Path) -> None:
    """The same claim, against a run rather than against the fold.

    The fold test above proves the ordering collapses correctly; this proves
    nothing between it and the graph quietly reorders anything. The visit
    sequence is read off the run's own progress events -- what it announced it
    was reading, in the order it announced it -- and compared with the order the
    index wrote before the run started.
    """
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
    # And the plan agrees with what actually happened, rather than only with
    # what was intended.
    plan = PlanStore(store.run_id)
    assert [item.chunk_id for item in plan.items()] == computed
    assert plan.summary() == {"done": len(computed)}


def test_seeding_twice_does_not_forget_progress(tmp_path: Path) -> None:
    """A resumed run seeds again. A seed that reset every status would tell the
    plan that finished work was pending."""
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
    # The order key never moves. What the index decided is still readable
    # underneath what the event asked for.
    assert plan.items()[0].order_key == len(order) - 1


def test_skip_leaves_the_queue_without_deleting_the_item(tmp_path: Path) -> None:
    """Never delete, only mark. A skipped unit that vanished from the plan would
    be indistinguishable from one the index never produced."""
    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    plan.record([PlanEvent(kind="skip", target=order[0], reason="generated code")])

    assert order[0] not in plan.pending()
    assert order[0] in [item.chunk_id for item in plan.items()]
    assert plan.summary()["skipped"] == 1


def test_the_plan_replays_exactly_from_its_event_log(tmp_path: Path) -> None:
    """(corpus, event log) is the whole input.

    Same order and same log, applied again, gives the same plan -- which is what
    makes an advisory run reproducible despite a model having been involved in
    it. The sequence number is assigned on write for exactly this reason: the
    order a model emitted things in is not an input.
    """
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

    # The same fold, in memory, over the same two inputs.
    assert apply_events(order, plan.events()) == stored

    # And a second run of the log over a fresh plan lands in the same place.
    other = ChunkStore(new_run().run_id)
    replayed = PlanStore(other.run_id)
    replayed.seed(order)
    replayed.record(plan.events())
    assert replayed.pending() == stored


def test_an_unknown_event_kind_is_dropped_rather_than_guessed_at(tmp_path: Path) -> None:
    """A kind the reducer does not understand is a change to traversal by
    another name."""
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
    """A chunk id is its content, so there is no smaller unit to point at.

    Recording the intent is honest; inventing chunk ids no index ever wrote
    would put units in the plan that nothing else in the run can resolve.
    """
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


# -- advisory mode -----------------------------------------------------------


def test_replan_is_absent_unless_asked_for() -> None:
    """A run cannot pay for a planner it did not ask for.

    Registered in `NODES` either way -- a breakpoint names a node, and the
    drawing of the agent should not change shape with a flag -- but only wired
    into the graph when the flag is on.
    """
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
    """The node returns no traversal. It writes to the log and nothing else.

    This is the whole safety argument for advisory mode, so it is asserted on
    the node's return value rather than inferred from behaviour: whatever the
    model says, `replan` cannot hand back a queue.
    """
    from agent.graph.nodes import NodeDeps, make_nodes
    from agent.llm import Outcome
    from agent.schema import PlanChange, PlanRevision

    store = _indexed(tmp_path)
    order = store.order()
    plan = PlanStore(store.run_id)
    plan.seed(order)

    class Planner:
        def call(self, schema, system, user, trace=None):  # noqa: ANN001
            return Outcome.of(
                PlanRevision(changes=[PlanChange(kind="skip", target=order[0], reason="생성된 코드")])
            )

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


def test_an_advisory_run_replays_from_its_event_log(tmp_path: Path) -> None:
    """The determinism claim, end to end.

    A model was involved, and the run is still a function of two recorded
    inputs. Replaying the stored log over the computed order reproduces the
    queue the run actually followed -- so an advisory run can be diffed against
    another the same way a computed one can, which is the property the whole
    design exists to keep.
    """
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
