"""One inspection, held open.

The graph used to be run by opening a store, a tool session and a checkpointer,
calling ``invoke`` once, and closing them again. Breakpoints break that shape:
the run stops mid-flight and waits for a person, and everything it was holding
has to still be there when it continues. So the lifetime moves into an object
the API can keep between requests.

Execution is streamed rather than invoked. ``invoke`` returns once, at the end,
which is enough for a report and useless for watching: the studio needs to know
which node is running *now*, and that only comes out of the stream.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

from ..cache import ResultCache, recipe_of
from ..config import AgentConfig
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..mcp.client import ALL_TOOLS, ToolSession, open_session
from ..promptstore import resolve as resolve_prompts
from ..schema import Finding, Report, RunStats
from ..trace import SpanRecorder, SpanStore
from ..tracing import apply_default_project
from .build import NODE_VISITS_PER_CHUNK, RECURSION_HEADROOM, build_graph
from .checkpoints import checkpoint_saver, summarise
from .nodes import NodeDeps, ProgressSink
from .state import initial_state

log = logging.getLogger(__name__)


class ParallelStep(ValueError):
    """State was edited at a step where several nodes ran at once.

    Not a failure of the edit -- a failure of the question. The API turns it
    into a 400 so the studio can say which step to edit instead.
    """


class InspectionSession:
    """A compiled graph plus everything it needs, kept open across steps.

    Constructing one opens the MCP subprocess and the checkpoint file; they stay
    open until :meth:`close`, which is what lets a run pause at a breakpoint and
    carry on without paying for the imports again or losing its tool session.
    """

    def __init__(
        self,
        *,
        run_id: str,
        root: Path,
        store: ChunkStore,
        config: AgentConfig,
        caller: StructuredCaller | None = None,
        emit: ProgressSink | None = None,
        index_stats: dict[str, int] | None = None,
        tools: ToolSession | None = None,
        spans: SpanStore | None = None,
        checkpoints: Path | None = None,
        breakpoints: Sequence[str] = (),
        breakpoints_after: Sequence[str] = (),
    ) -> None:
        self.run_id = run_id
        self.store = store
        self.config = config
        self._emit: ProgressSink = emit if emit is not None else (lambda event, payload: None)
        self._index_stats = index_stats or {}
        self._values: dict[str, Any] = {}
        self._next: tuple[str, ...] = ()
        self._checkpoint_id: str | None = None
        self._last_node: str | None = None
        self._owned_tools: ToolSession | None = None

        # Group traces under one project so a run does not land in LangSmith's
        # `default` alongside everything else on the machine. No-op when tracing
        # is off, and never overrides an explicit LANGSMITH_PROJECT.
        apply_default_project()

        # Ask the endpoint how much room there is, once, before any of it is
        # spent. Every budget in this package used to be a character count
        # invented against a window nobody had read; without this call the
        # derived one falls back to exactly that number and `scout` never sees a
        # unit it considers too large, because nothing ever is.
        window = config.resolve_window()
        if window:
            log.info("context window %d tokens; budgeting %d characters of prompt", window, config.input_chars())
        else:
            log.info("endpoint did not report a context window; budgeting %d characters", config.input_chars())

        # Resolved once, here, rather than per call: a prompt edited while a run
        # is going must not leave half its chunks analysed against one prompt
        # and half against another.
        self.prompts = resolve_prompts(config.prompts_file)

        # Results from earlier runs over the same code. Keyed on the recipe as
        # well as the chunk -- same model, same specialists, same prompts --
        # because serving a result produced by a narrower configuration is a
        # false negative that looks like a cache hit.
        self._cache: ResultCache | None = None
        if config.cache_results and config.model:
            self._cache = ResultCache(
                config.cache_file,
                recipe_of(model=config.model, lenses=config.lenses, prompts=self.prompts),
            )

        deps = NodeDeps(
            store=store,
            cache=self._cache,
            config=config,
            caller=caller if caller is not None else StructuredCaller(config),
            root=root,
            emit=self._emit,
            run_id=run_id,
            tools=tools,
            prompts=self.prompts,
            subsystems=_subsystems(store),
        )

        # The agent consumes its own MCP server. Opened for the whole session so
        # the subprocess and its imports are paid for once, not per finding --
        # and so a run paused at a breakpoint still has its tools when it
        # resumes. Absent tools mean verification runs from context, which is a
        # supported mode.
        if tools is None and config.enable_tools:
            self._owned_tools = open_session(
                run_root=root,
                index_db=store.path,
                sandbox=config.sandbox,
                allowed=ALL_TOOLS,
            )
            deps.tools = self._owned_tools

        # One thread per run, so a run's history is its own and stepping through
        # it afterwards shows that run's states and nobody else's.
        self._saver = checkpoint_saver(checkpoints) if checkpoints is not None else None

        # Interrupts are implemented by the checkpointer -- without one there is
        # nowhere to stop, so breakpoints are dropped rather than raising.
        self.breakpoints = list(breakpoints) if self._saver is not None else []
        self.breakpoints_after = list(breakpoints_after) if self._saver is not None else []
        if (breakpoints or breakpoints_after) and self._saver is None:
            log.warning("breakpoints ignored: this run has no checkpoint file")

        self.order = store.order()
        self._invocation: dict[str, Any] = {
            #: One chunk costs a handful of node visits. Generous, so a large
            #: upload is bounded by the queue rather than by LangGraph.
            "recursion_limit": len(self.order) * NODE_VISITS_PER_CHUNK + RECURSION_HEADROOM,
            "callbacks": [SpanRecorder(spans)] if spans is not None else None,
            # The ceiling on requests actually in flight. A wave of four chunks
            # times four lenses is sixteen analyses ready at once, and an
            # endpoint asked for sixteen at once answers all of them slowly.
            # LangGraph turns this into a semaphore around its executor.
            "max_concurrency": max(1, config.max_concurrency),
        }
        if self._saver is not None:
            # ``checkpoint_ns`` is spelled out because writing state requires
            # it and running does not. No subgraphs here, so it is the root
            # namespace either way.
            self._invocation["configurable"] = {"thread_id": run_id, "checkpoint_ns": ""}

        self._app = build_graph(
            deps,
            checkpointer=self._saver,
            breakpoints=self.breakpoints,
            breakpoints_after=self.breakpoints_after,
        )

    # -- lifetime ------------------------------------------------------------

    def __enter__(self) -> "InspectionSession":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def warm_from_cache(self) -> int:
        """Fill this run's store with what earlier runs already established.

        Before the graph, not inside it: a warmed chunk is marked inspected, so
        `plan` skips it by the ordinary path and it lands in `chunks_cached`
        where the summary already reports it. No node has to know this happened.
        """
        if self._cache is None:
            return 0
        warmed = self._cache.warm(self.store, self.order)
        if warmed:
            log.info("reused %d of %d units from earlier runs", warmed, len(self.order))
        return warmed

    def close(self) -> None:
        if self._cache is not None:
            self._cache.close()
            self._cache = None
        if self._owned_tools is not None:
            self._owned_tools.close()
            self._owned_tools = None
        if self._saver is not None:
            self._saver.conn.close()
            self._saver = None

    # -- running -------------------------------------------------------------

    def initial(self) -> dict[str, Any]:
        """The state a fresh run would begin from.

        Answered without running anything, because the studio shows it as the
        run's input before there is a run: the queue it would work through is
        the most useful thing to see, and the most useful thing to narrow.
        """
        return dict(initial_state(self.order, len(self.order), self._index_stats))

    def start(self, values: dict[str, Any] | None = None) -> None:
        """Run from the beginning, stopping at the first breakpoint.

        ``values`` overrides fields of the starting state -- a shorter queue to
        try one chunk, say. Merged rather than replacing it, so naming one field
        does not silently drop the tallies the rest of the graph reads.
        """
        # Before `initial()`, which reads what is already inspected to build the
        # queue: warming after it would compute a queue holding chunks that were
        # about to become free.
        self.warm_from_cache()
        state = self.initial()
        if values:
            state.update(values)
        self._values = state
        self._stream(state, self._invocation)

    def resume(self, values: dict[str, Any] | None = None, checkpoint_id: str | None = None) -> None:
        """Carry on from where the graph stopped.

        ``values`` is written over the state first, which is the whole point of
        stopping: a person looks at what the graph is about to do, changes it,
        and lets it go. ``checkpoint_id`` picks an earlier point instead of the
        latest one, which branches the thread there.
        """
        config = self._config_at(checkpoint_id)
        if values:
            # Told whose write this stands in for, because it decides where the
            # graph goes next. Left to infer, LangGraph attributes the write to
            # the step before the one that just ran, and the run repeats a node
            # it had already finished.
            updated = self._app.update_state(config, values, as_node=self._writer(config))
            config = {**config, "configurable": updated["configurable"]}
        self._stream(None, config)

    def _writer(self, config: dict[str, Any]) -> str | None:
        """The node that produced the checkpoint being resumed from.

        Refuses rather than guesses when several nodes ran at once. LangGraph
        needs one node to attribute the write to, and at a fan-out step there
        genuinely is no answer: the specialists wrote that state between them,
        and picking one of them decides where the graph goes next. Editing at
        the joins -- `locate`, `reduce`, `plan` -- is always well defined.
        """
        if self._saver is None:
            return None
        snapshot = self._app.get_state(config)
        if not snapshot.parent_config:
            return self._last_node
        # What was queued at the parent is what wrote this.
        queued = list(self._app.get_state(snapshot.parent_config).next)
        if len(queued) > 1:
            raise ParallelStep(
                f"this step ran {len(queued)} tasks at once ({', '.join(sorted(set(queued)))}); "
                "edit the state at the step that joins them instead"
            )
        return queued[0] if queued else self._last_node

    def _config_at(self, checkpoint_id: str | None) -> dict[str, Any]:
        if checkpoint_id is None:
            return self._invocation
        return {
            **self._invocation,
            "configurable": {"thread_id": self.run_id, "checkpoint_ns": "", "checkpoint_id": checkpoint_id},
        }

    def _stream(self, payload: Any, config: dict[str, Any]) -> None:
        """Drive the graph, reporting each node as it starts and finishes."""
        for mode, frame in self._app.stream(payload, config=config, stream_mode=["debug", "values"]):
            if mode == "values":
                if isinstance(frame, dict):
                    self._values = frame
            else:
                self._report(frame)
        self._refresh()

    def _report(self, frame: Any) -> None:
        """Turn one LangGraph debug frame into a progress event.

        Wrapped because a malformed frame must not take the run down with it --
        this is the watching, not the work.
        """
        if not isinstance(frame, dict):
            return
        body = frame.get("payload") or {}
        step = frame.get("step")
        try:
            kind = frame.get("type")
            if kind == "task":
                self._emit("node_started", {"node": body.get("name"), "step": step})
            elif kind == "task_result":
                error = body.get("error")
                self._last_node = body.get("name")
                self._emit(
                    "node_finished",
                    {
                        "node": body.get("name"),
                        "step": step,
                        "error": str(error) if error else None,
                        # What the node wrote, counted rather than copied: a
                        # progress event is not a place to ship the findings.
                        "updates": summarise(dict(body.get("result") or [])),
                    },
                )
            elif kind == "checkpoint":
                configurable = (body.get("config") or {}).get("configurable") or {}
                self._emit(
                    "checkpoint",
                    {
                        "checkpoint_id": configurable.get("checkpoint_id"),
                        "step": step,
                        # Nothing in a checkpoint names the node that wrote it,
                        # but we just watched it finish.
                        "node": self._last_node,
                        "next": [_name(task) for task in body.get("next") or ()],
                    },
                )
        except Exception:  # noqa: BLE001 - reporting must not break the run
            log.debug("could not report a debug frame", exc_info=True)

    def _refresh(self) -> None:
        """Read back where the graph stopped, so we know if it is paused."""
        if self._saver is None:
            self._next = ()
            return
        snapshot = self._app.get_state({"configurable": {"thread_id": self.run_id}})
        self._next = tuple(snapshot.next)
        self._checkpoint_id = (snapshot.config.get("configurable") or {}).get("checkpoint_id")

    # -- where it stopped ----------------------------------------------------

    @property
    def interrupted(self) -> bool:
        """Paused at a breakpoint, with work still queued."""
        return bool(self._next)

    @property
    def next_nodes(self) -> list[str]:
        return list(self._next)

    @property
    def checkpoint_id(self) -> str | None:
        return self._checkpoint_id

    @property
    def values(self) -> dict[str, Any]:
        return self._values

    def report(self) -> Report:
        """The findings, read back from the store rather than from graph state.

        A run that was resumed or partially cached returns everything known
        about the tree, not only what this session happened to produce.
        """
        raw = self._values.get("stats") or {}
        stats = RunStats(**{k: v for k, v in raw.items() if k in RunStats.model_fields})
        report = Report(
            run_id=self.run_id,
            findings=[Finding.model_validate(payload) for payload in self.store.findings()],
            stats=stats,
        )
        report.findings = report.sorted_findings()
        return report


def _subsystems(store: ChunkStore) -> dict[str, int]:
    """Chunk id to subsystem, read from the graph written beside the index.

    Absent for a run indexed before the graph existed, and that is fine -- the
    wave then fills in queue order, which is what it did before. Not worth
    building on the spot here: it decides a preference, not a correctness
    property.
    """
    from ..knowledge import GRAPH_FILE, read_graph

    loaded = read_graph(store.path.parent / GRAPH_FILE)
    if loaded is None:
        return {}
    _, communities = loaded
    return {member: community.id for community in communities for member in community.members}


def _name(task: Any) -> str:
    """A queued task's node name, however LangGraph spelled it."""
    if isinstance(task, str):
        return task
    if isinstance(task, dict):
        return str(task.get("name", ""))
    return str(getattr(task, "name", task))
