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
import time
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

#: How long a stream opened on a run that is not in flight waits for one to
#: begin before saying so.
#:
#: Every start is "attach, then POST", and the POST computes the traversal order
#: before it spawns -- so the reader is routinely asked to sit through work that
#: takes longer than one poll. Bounded, because a tab watching a run nobody
#: starts would otherwise hold a response open for the life of the process.
STREAM_START_GRACE_SECONDS = 45.0

#: How long a channel with no worker and no listener is kept before it is
#: forgotten. `_channels` is keyed by run id and was never emptied, and a GET on
#: `/events` allocates one for any run -- so merely viewing runs grew it.
CHANNEL_IDLE_SECONDS = 15 * 60


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
    #: The thread on this channel, so shutdown can wait for it rather than
    #: killing it where it stands.
    worker: Optional[threading.Thread] = None
    #: When a worker or a listener last arrived, for the sweep below.
    touched: float = field(default_factory=time.monotonic)

    _listeners: "set[queue.Queue[dict[str, Any]]]" = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def live(self) -> bool:
        """Whether a worker is on this channel right now.

        The one definition, used by `_live_channel`, by `claim` and by the SSE
        reader. `finished` alone cannot answer it: nothing clears the flag when
        a run ends, so between two runs it is a true statement about the wrong
        run -- which is what closed a stream a second after it attached.
        """
        return self.claimed and not self.finished.is_set()

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
            self.touched = time.monotonic()
        try:
            yield mine
        finally:
            with self._lock:
                self._listeners.discard(mine)

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._listeners)

    def claim(self) -> bool:
        """Take this channel for a new worker, or say somebody else has it.

        The asking and the taking in one step. `/inspect` used to ask
        `_live_channel` and spawn several lines later, with a traversal-order
        computation in between -- so two requests landing together both passed
        and both put a worker on one run, sharing a store and a thread id while
        the second reset the debug record the first was writing.
        """
        with self._lock:
            if self.live:
                return False
            self._reclaim()
            return True

    def reclaim(self) -> None:
        """Ready this channel for another worker, keeping listeners attached.

        The watcher holds this object, so it is reset rather than replaced --
        swapping it would leave whoever is watching listening to a queue nothing
        writes to any more.
        """
        with self._lock:
            self._reclaim()

    def _reclaim(self) -> None:
        """The body of `reclaim`, with the lock already held."""
        # Only `commands`: a stale abort would misfire on the new worker. The
        # listener queues are left alone, and used to be drained -- which threw
        # away the previous run's unread `run_finished` whenever a start landed
        # inside the reader's one-second poll. Queues are FIFO, so a listener
        # that survives sees the tail of the run that ended and then the new
        # run's frames, in that order, which is what the reducer expects.
        while True:
            try:
                self.commands.get_nowait()
            except queue.Empty:
                break
        self.finished.clear()
        self.waiting.clear()
        # Cleared with the rest of it, and it was not. `_channel` caches this
        # object per run id for the life of the process, so a run that had once
        # been cancelled kept a set flag for ever: every later `/inspect` on it
        # broke at the first frame and finished immediately as `cancelled` with
        # nothing inspected. Stopping a scan appeared to break that run
        # permanently -- reclaiming the channel is exactly where the last stop
        # stops applying.
        self.cancelled.clear()
        self.error = None
        self.claimed = True
        self.touched = time.monotonic()


def _channel(run_id: str) -> RunChannel:
    with _channels_lock:
        _sweep()
        return _channels.setdefault(run_id, RunChannel())


def _sweep() -> None:
    """Forget channels with no worker and no listener. Caller holds the lock.

    A live channel is never swept: the worker holds it, and `/cancel` finds it
    through this dict.
    """
    now = time.monotonic()
    for run_id, channel in list(_channels.items()):
        if channel.live or channel.listeners:
            continue
        if now - channel.touched > CHANNEL_IDLE_SECONDS:
            del _channels[run_id]


def _live_channel(run_id: str) -> Optional[RunChannel]:
    """The run's channel if a worker is still on it.

    Watching is not running: the studio opens the stream when a run is selected,
    long before anyone presses start, and that must not read as in flight.
    """
    with _channels_lock:
        channel = _channels.get(run_id)
    if channel is None or not channel.live:
        return None
    return channel


def drain(timeout: float) -> list[str]:
    """Ask every live worker to stop, and give it a bounded moment.

    A worker is a daemon thread, so shutdown kills it mid-frame: the session
    never closes, its MCP subprocess is orphaned, and the row stays `inspecting`
    until the next boot marks it failed. Cancelling ends it as `cancelled` with
    what it found, which is what 중단 already does.
    """
    with _channels_lock:
        live = [(run_id, channel) for run_id, channel in _channels.items() if channel.live]
    for _, channel in live:
        channel.cancelled.set()
        if channel.waiting.is_set():
            channel.commands.put({"action": "abort"})
    # Joined outside the lock: a worker still publishing takes its own.
    deadline = time.monotonic() + timeout
    for _, channel in live:
        worker = channel.worker
        if worker is not None:
            worker.join(max(0.0, deadline - time.monotonic()))
    return [run_id for run_id, _ in live]
