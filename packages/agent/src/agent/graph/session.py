from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Sequence

from ..cache import ResultCache, recipe_of
from ..config import AgentConfig
from ..harness import record as record_config
from ..index.reach import stamp as stamp_reach
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
from .plan import PlanStore
from .state import initial_state

log = logging.getLogger(__name__)


class ParallelStep(ValueError):
    pass


class InspectionSession:
    def __init__(
        self,
        *,
        run_id: str,
        files: Mapping[str, str],
        store: ChunkStore,
        config: AgentConfig,
        caller: StructuredCaller | None = None,
        emit: ProgressSink | None = None,
        index_stats: dict[str, int] | None = None,
        tools: ToolSession | None = None,
        spans: SpanStore | None = None,
        checkpoints: bool = False,
        breakpoints: Sequence[str] = (),
        breakpoints_after: Sequence[str] = (),
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self.run_id = run_id
        self.store = store
        self.config = config
        self._emit: ProgressSink = emit if emit is not None else (lambda event, payload: None)
        self._cancelled: Callable[[], bool] = cancelled if cancelled is not None else (lambda: False)
        self.stopped = False
        self._index_stats = index_stats or {}
        self._values: dict[str, Any] = {}
        self._next: tuple[str, ...] = ()
        self._checkpoint_id: str | None = None
        self._last_node: str | None = None
        self._owned_tools: ToolSession | None = None

        apply_default_project()

        window = config.resolve_window()
        if window:
            log.info("context window %d tokens; budgeting %d characters of prompt", window, config.input_chars())
        else:
            log.info("endpoint did not report a context window; budgeting %d characters", config.input_chars())

        self.prompts = resolve_prompts(config.prompts_file)

        self._cache: ResultCache | None = None
        if config.cache_results and config.model:
            self._cache = ResultCache(
                recipe_of(
                    model=config.model,
                    lenses=config.lenses,
                    prompts=self.prompts,
                    reasoning_effort=config.reasoning_effort,
                    max_tokens=config.max_tokens,
                ),
                config,
            )

        self.config_hash = record_config(config)
        try:
            from ..runs import Run

            Run(store.run_id).write_meta(config_hash=self.config_hash)
        except Exception:  # pragma: no cover - provenance must not break a run
            log.debug("could not record the config hash on run %s", store.run_id, exc_info=True)

        self.plan = PlanStore(store.run_id, config)

        deps = NodeDeps(
            store=store,
            cache=self._cache,
            config=config,
            caller=caller if caller is not None else StructuredCaller(config),
            files=files,
            emit=self._emit,
            run_id=run_id,
            tools=tools,
            prompts=self.prompts,
            subsystems=_subsystems(store),
            plan=self.plan,
            cancelled=self._cancelled,
        )

        if tools is None and config.enable_tools:
            self._owned_tools = open_session(
                run_id=run_id,
                database_url=config.database_url,
                sandbox=config.sandbox,
                allowed=ALL_TOOLS,
            )
            deps.tools = self._owned_tools

        self._conn, self._saver = checkpoint_saver(config.database_url) if checkpoints else (None, None)

        self.breakpoints = list(breakpoints) if self._saver is not None else []
        self.breakpoints_after = list(breakpoints_after) if self._saver is not None else []
        if (breakpoints or breakpoints_after) and self._saver is None:
            log.warning("breakpoints ignored: this session was built without a checkpointer")

        self.order = store.order()

        self.plan.seed(self.order)

        self._invocation: dict[str, Any] = {
            "recursion_limit": len(self.order) * NODE_VISITS_PER_CHUNK + RECURSION_HEADROOM,
            "callbacks": [SpanRecorder(spans)] if spans is not None else None,
            "max_concurrency": max(1, config.max_concurrency),
        }
        if self._saver is not None:
            self._invocation["configurable"] = {"thread_id": run_id, "checkpoint_ns": ""}

        self._app = build_graph(
            deps,
            checkpointer=self._saver,
            breakpoints=self.breakpoints,
            breakpoints_after=self.breakpoints_after,
        )

    def __enter__(self) -> "InspectionSession":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def warm_from_cache(self) -> int:
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
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._saver = None

    def initial(self) -> dict[str, Any]:
        return dict(initial_state(self.order, len(self.order), self._index_stats))

    def start(self, values: dict[str, Any] | None = None, warm: bool = True) -> None:
        if warm:
            self.warm_from_cache()
        state = self.initial()
        if values:
            state.update(values)
        self._values = state
        self._stream(state, self._invocation)

    def resume(self, values: dict[str, Any] | None = None, checkpoint_id: str | None = None) -> None:
        config = self._config_at(checkpoint_id)
        if values:
            updated = self._app.update_state(config, values, as_node=self._writer(config))
            config = {**config, "configurable": updated["configurable"]}
        self._stream(None, config)

    def _writer(self, config: dict[str, Any]) -> str | None:
        if self._saver is None:
            return None
        snapshot = self._app.get_state(config)
        if not snapshot.parent_config:
            return self._last_node
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
        for mode, frame in self._app.stream(payload, config=config, stream_mode=["debug", "values"]):
            if mode == "values":
                if isinstance(frame, dict):
                    self._values = frame
            else:
                self._report(frame)
            if self._cancelled():
                self.stopped = True
                break
        self._refresh()

    def _report(self, frame: Any) -> None:
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
                        "node": self._last_node,
                        "next": [_name(task) for task in body.get("next") or ()],
                    },
                )
        except Exception:  # noqa: BLE001 - reporting must not break the run
            log.debug("could not report a debug frame", exc_info=True)

    def _refresh(self) -> None:
        if self._saver is None:
            self._next = ()
            return
        snapshot = self._app.get_state({"configurable": {"thread_id": self.run_id}})
        self._next = tuple(snapshot.next)
        self._checkpoint_id = (snapshot.config.get("configurable") or {}).get("checkpoint_id")

    @property
    def interrupted(self) -> bool:
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
        raw = self._values.get("stats") or {}
        stats = RunStats(**{k: v for k, v in raw.items() if k in RunStats.model_fields})
        report = Report(
            run_id=self.run_id,
            findings=[
                Finding.model_validate(payload)
                for payload in stamp_reach(self.store.findings(), self.store.reach())
            ],
            stats=stats,
        )
        report.findings = report.sorted_findings()
        return report


def _subsystems(store: ChunkStore) -> dict[str, int]:
    from ..knowledge import read_graph

    loaded = read_graph(store.run_id)
    if loaded is None:
        return {}
    _, communities = loaded
    return {member: community.id for community in communities for member in community.members}


def _name(task: Any) -> str:
    if isinstance(task, str):
        return task
    if isinstance(task, dict):
        return str(task.get("name", ""))
    return str(getattr(task, "name", task))
