from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


_channels: Dict[str, RunChannel] = {}
_channels_lock = threading.Lock()
SSE_POLL_SECONDS = 1.0
SSE_KEEPALIVE_SECONDS = 15.0
INTERRUPT_TIMEOUT_SECONDS = 30 * 60
STREAM_START_GRACE_SECONDS = 45.0
CHANNEL_IDLE_SECONDS = 15 * 60


@dataclass
class RunChannel:
    commands: "queue.Queue[dict[str, Any]]" = field(default_factory=queue.Queue)
    finished: threading.Event = field(default_factory=threading.Event)
    waiting: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)
    claimed: bool = False
    error: Optional[str] = None
    worker: Optional[threading.Thread] = None
    touched: float = field(default_factory=time.monotonic)
    _listeners: "set[queue.Queue[dict[str, Any]]]" = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def live(self) -> bool:
        return self.claimed and not self.finished.is_set()

    def publish(self, message: Dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener.put(message)

    @contextmanager
    def listen(self) -> "Iterator[queue.Queue[dict[str, Any]]]":
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
        with self._lock:
            if self.live:
                return False
            self._reclaim()
            return True

    def reclaim(self) -> None:
        with self._lock:
            self._reclaim()

    def _reclaim(self) -> None:
        while True:
            try:
                self.commands.get_nowait()
            except queue.Empty:
                break
        self.finished.clear()
        self.waiting.clear()
        self.cancelled.clear()
        self.error = None
        self.claimed = True
        self.touched = time.monotonic()


def _channel(run_id: str) -> RunChannel:
    with _channels_lock:
        _sweep()
        return _channels.setdefault(run_id, RunChannel())


def _sweep() -> None:
    now = time.monotonic()
    for run_id, channel in list(_channels.items()):
        if channel.live or channel.listeners:
            continue
        if now - channel.touched > CHANNEL_IDLE_SECONDS:
            del _channels[run_id]


def _live_channel(run_id: str) -> Optional[RunChannel]:
    with _channels_lock:
        channel = _channels.get(run_id)
    if channel is None or not channel.live:
        return None
    return channel


def drain(timeout: float) -> list[str]:
    with _channels_lock:
        live = [(run_id, channel) for run_id, channel in _channels.items() if channel.live]
    for _, channel in live:
        channel.cancelled.set()
        if channel.waiting.is_set():
            channel.commands.put({"action": "abort"})
    deadline = time.monotonic() + timeout
    for _, channel in live:
        worker = channel.worker
        if worker is not None:
            worker.join(max(0.0, deadline - time.monotonic()))
    return [run_id for run_id, _ in live]
