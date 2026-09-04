"""What keeps a long run's terminal readable.

A batch prints one progress bar and, occasionally, a line about a file. Getting
that wrong is not cosmetic: the bar used to vanish for the rest of the run after
a single failure, and Joern's own chatter used to bury it entirely.
"""

from __future__ import annotations

import os

import pytest

from ssat.cli.logger import SimpleLogger
from ssat.cpg.embedded import _quiet_joern_logging

tqdm = pytest.importorskip("tqdm")


def test_messages_do_not_close_the_progress_bar():
    """One error mid-batch used to remove the bar for every remaining file.

    ``error`` closed the bar and dropped the reference, and nothing reopened
    it, so ``update_progress`` silently no-opped from then on.
    """
    logger = SimpleLogger()
    logger.start_progress(3)
    try:
        logger.update_progress(1)
        logger.error("file 2 failed")
        logger.info("carrying on")

        assert logger.progress_bar is not None, "a message closed the progress bar"

        logger.update_progress(2)
        assert logger.progress_bar.n == 2, "the bar stopped tracking after a message"
    finally:
        logger.stop_progress()

    assert logger.progress_bar is None


def test_stop_progress_is_what_closes_the_bar():
    logger = SimpleLogger()
    logger.start_progress(1)
    logger.stop_progress()
    assert logger.progress_bar is None
    logger.info("no bar, still prints")  # must not raise


def test_joern_logging_defaults_to_warn(monkeypatch):
    """Joern's log4j2.xml reads ``${env:SL_LOGGING_LEVEL:-info}``.

    Leaving it at ``info`` is what put ~95 lines per source file on the console.
    """
    monkeypatch.delenv("SL_LOGGING_LEVEL", raising=False)
    _quiet_joern_logging()
    assert os.environ["SL_LOGGING_LEVEL"] == "warn"


def test_explicit_joern_log_level_wins(monkeypatch):
    """A noisy run stays one environment variable away."""
    monkeypatch.setenv("SL_LOGGING_LEVEL", "debug")
    _quiet_joern_logging()
    assert os.environ["SL_LOGGING_LEVEL"] == "debug"
