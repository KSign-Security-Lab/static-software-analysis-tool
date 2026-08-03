"""The single place a model gets called.

vLLM runs as a separate OpenAI-compatible server, so this package needs the
client and not ``vllm`` itself. Two structured-output paths exist and both are
handled here rather than at call sites:

``response_format={"type": "json_schema", ...}``
    The OpenAI-standard form, and what ``with_structured_output(method=
    "json_schema")`` emits. Confirmed working against a served model.

``extra_body={"structured_outputs": {"json": schema}}``
    vLLM's own form. Kept as a fallback because guided decoding support varies
    between vLLM builds and backends (``xgrammar``, ``guidance``).

Keeping both behind one function means switching is a configuration change, not
a refactor.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypeVar

from langchain_openai import ChatOpenAI
from openai import LengthFinishReasonError
from pydantic import BaseModel

from .config import AgentConfig

log = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

StructuredMethod = Literal["json_schema", "function_calling"]

#: Tried in order. ``json_schema`` is real constrained decoding; the tool-calling
#: path is a fallback for endpoints that expose function calling but not guided
#: JSON.
STRUCTURED_METHODS: tuple[StructuredMethod, ...] = ("json_schema", "function_calling")


def make_llm(config: AgentConfig) -> ChatOpenAI:
    """A client for the configured endpoint.

    ``require_model`` is called here so a missing model fails at construction
    with an actionable message, rather than at the first request part-way
    through a long run.
    """
    return ChatOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,  # type: ignore[arg-type]
        model=config.require_model(),
        temperature=config.temperature,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        # The field is `max_tokens`, but it is aliased and the constructor only
        # accepts the alias.
        max_completion_tokens=config.max_tokens,
    )


class StructuredCaller:
    """Calls the model and returns a validated pydantic object, or None.

    None rather than an exception: one chunk whose output will not parse must
    not abort an inspection that is forty minutes in. The failure is counted and
    reported instead.
    """

    def __init__(self, config: AgentConfig, llm: ChatOpenAI | None = None) -> None:
        self.config = config
        self.llm = llm if llm is not None else make_llm(config)
        #: Which method worked, remembered after the first success so later
        #: calls do not re-pay for probing a path the endpoint rejects.
        self._method: StructuredMethod | None = None

    def _runnable(self, schema: type[ModelT], method: StructuredMethod) -> Any:
        return self.llm.with_structured_output(schema, method=method)

    def call(self, schema: type[ModelT], system: str, user: str) -> ModelT | None:
        """One structured call. Returns None if nothing usable came back."""
        messages = [("system", system), ("human", user)]
        methods: tuple[StructuredMethod, ...] = (self._method,) if self._method else STRUCTURED_METHODS

        for method in methods:
            try:
                result = self._runnable(schema, method).invoke(messages)
            except LengthFinishReasonError:
                # Guided decoding guarantees the shape, not termination: a model
                # too small for the schema emits a valid prefix until it runs
                # out of room. Worth naming, because it looks like a protocol
                # failure and is not one.
                log.warning(
                    "%s did not finish a %s object within max_tokens -- the model is probably "
                    "too small for this schema. Try a larger one, or raise AGENT_MAX_TOKENS.",
                    method,
                    schema.__name__,
                )
                continue
            except Exception as err:  # noqa: BLE001 - any client/model failure is the same to us
                log.warning("structured call failed via %s: %s", method, err)
                if "tool-call-parser" in str(err):
                    # vLLM rejects tool calling unless the server was started
                    # with a parser for the model family, so this fallback is
                    # unavailable rather than broken.
                    log.warning(
                        "the endpoint needs --tool-call-parser for the function_calling fallback; "
                        "json_schema is the supported path"
                    )
                continue
            if isinstance(result, schema):
                self._method = method
                return result
            log.warning("structured call via %s returned %s, not %s", method, type(result), schema.__name__)

        # A remembered method that has started failing should not stay pinned.
        if self._method is not None:
            self._method = None
        return None
