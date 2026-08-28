"""The in-process link with a running inspection.

An inspection runs on a worker thread while requests are served on the event
loop, so progress crosses that boundary through plain thread-safe queues rather
than asyncio ones.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


#: In-process only. A restart loses the stream but not the run: the report is on
#: disk, and re-requesting the inspection resumes from the store.
_channels: Dict[str, RunChannel] = {}

_channels_lock = threading.Lock()

#: How long the SSE generator waits on the queue before emitting a keep-alive.
#: Proxies close an idle connection, and a chunk can take longer than that.
SSE_POLL_SECONDS = 1.0

SSE_KEEPALIVE_SECONDS = 15.0

#: How long a run paused at a breakpoint waits to be told what to do before it
#: gives up and lets go of its tools. A person is expected to answer; an
#: abandoned tab is not, and it would hold an MCP subprocess open indefinitely.
INTERRUPT_TIMEOUT_SECONDS = 30 * 60


@dataclass
class RunChannel:
    """The two-way link with one in-flight run.

    Plain thread-safe queues rather than asyncio ones: the run is on a worker
    thread and the requests are on the event loop, so both have to work across
    that boundary. ``publish`` carries progress out; ``commands`` carries the
    answer back in when the run stops at a breakpoint and waits.

    Progress fans out: every listener gets its own queue and every event is
    copied into all of them. There used to be a single queue that each reader
    popped from, which meant two readers on one run *split* its events -- each
    frame reaching exactly one of them, and neither seeing a whole run. Two
    browser tabs was enough to trigger it.
    """

    commands: "queue.Queue[dict[str, Any]]" = field(default_factory=queue.Queue)
    finished: threading.Event = field(default_factory=threading.Event)
    #: Set while the run is stopped at a breakpoint, so a resume request knows
    #: whether to steer the live worker or start a new one.
    waiting: threading.Event = field(default_factory=threading.Event)
    #: Asked to stop, whether or not it is waiting for anything.
    #:
    #: `commands` could not answer this. It is only read by a worker parked at a
    #: breakpoint, so 중단 on an ordinary scan put a message into a queue nobody
    #: was reading and the request was refused with "not stopped at a
    #: breakpoint" -- which is true and useless, since the new surface sets no
    #: breakpoints and a run therefore never parks. An event can be checked
    #: rather than waited for, which is what stopping a *running* graph needs.
    cancelled: threading.Event = field(default_factory=threading.Event)
    #: Whether a worker was ever put on this channel. A channel opened by a
    #: listener is not a run in flight -- without this, watching a run before
    #: starting it would make it look like it had already started.
    claimed: bool = False
    error: Optional[str] = None

    _listeners: "set[queue.Queue[dict[str, Any]]]" = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def publish(self, message: Dict[str, Any]) -> None:
        """Hand one event to every listener.

        Events published with nobody attached are dropped rather than buffered.
        That is deliberate: the stream is documented as not replayable, clients
        read their state over REST and use this only as a signal, and an
        unbounded backlog for a listener that may never arrive is a leak.
        """
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener.put(message)

    @contextmanager
    def listen(self) -> "Iterator[queue.Queue[dict[str, Any]]]":
        """Attach a queue for as long as one reader is reading it."""
        mine: "queue.Queue[dict[str, Any]]" = queue.Queue()
        with self._lock:
            self._listeners.add(mine)
        try:
            yield mine
        finally:
            with self._lock:
                self._listeners.discard(mine)

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._listeners)

    def reclaim(self) -> None:
        """Ready this channel for another worker, keeping listeners attached.

        The watcher holds this object, so it is reset rather than replaced --
        swapping it would leave whoever is watching listening to a queue nothing
        writes to any more.
        """
        with self._lock:
            stale = list(self._listeners)
        for listener in [*stale, self.commands]:
            while True:
                try:
                    listener.get_nowait()
                except queue.Empty:
                    break
        self.finished.clear()
        self.waiting.clear()
        self.error = None
        self.claimed = True


def _channel(run_id: str) -> RunChannel:
    with _channels_lock:
        return _channels.setdefault(run_id, RunChannel())


def _live_channel(run_id: str) -> Optional[RunChannel]:
    """The run's channel if a worker is still on it.

    Watching is not running: the studio opens the stream when a run is selected,
    long before anyone presses start, and that must not read as in flight.
    """
    with _channels_lock:
        channel = _channels.get(run_id)
    if channel is None or not channel.claimed or channel.finished.is_set():
        return None
    return channel
