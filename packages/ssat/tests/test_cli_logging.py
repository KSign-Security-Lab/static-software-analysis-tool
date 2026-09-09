from __future__ import annotations

import os

import pytest

from ssat.cli.logger import SimpleLogger
from ssat.cpg.embedded import _quiet_joern_logging

tqdm = pytest.importorskip("tqdm")


def test_messages_do_not_close_the_progress_bar():
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
    logger.info("no bar, still prints")


def test_joern_logging_defaults_to_warn(monkeypatch):
    monkeypatch.delenv("SL_LOGGING_LEVEL", raising=False)
    _quiet_joern_logging()
    assert os.environ["SL_LOGGING_LEVEL"] == "warn"


def test_explicit_joern_log_level_wins(monkeypatch):
    monkeypatch.setenv("SL_LOGGING_LEVEL", "debug")
    _quiet_joern_logging()
    assert os.environ["SL_LOGGING_LEVEL"] == "debug"
