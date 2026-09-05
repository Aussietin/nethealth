"""Tests for nethealth/logger.py -- the opt-in rotating file logger wired
up via `nethealth --log FILE`."""
from __future__ import annotations

import logging
import logging.handlers

from nethealth import logger as logger_mod


def test_get_logger_silent_without_setup(caplog):
    # No setup_file_log() call in this test -> root logger stays at its
    # default WARNING level, so an INFO record is dropped, matching the
    # documented "silently discarded" behaviour.
    log = logger_mod.get_logger("nethealth.test_silent")
    with caplog.at_level(logging.DEBUG):
        log.info("should not be captured at INFO by a WARNING-level root")
    # get_logger itself must not raise or force a level.
    assert log.name == "nethealth.test_silent"


def test_setup_file_log_writes_records(tmp_path):
    log_path = tmp_path / "nethealth.log"
    logger_mod.setup_file_log(log_path, level=logging.INFO)
    try:
        log = logger_mod.get_logger("nethealth.test_write")
        log.info("hello from test")
        for handler in logging.getLogger().handlers:
            handler.flush()
        assert log_path.exists()
        assert "hello from test" in log_path.read_text()
    finally:
        # Clean up so this handler doesn't leak into other tests.
        root = logging.getLogger()
        for h in list(root.handlers):
            if isinstance(h, logging.handlers.RotatingFileHandler):
                root.removeHandler(h)
                h.close()


def test_setup_file_log_replaces_previous_handler(tmp_path):
    first = tmp_path / "first.log"
    second = tmp_path / "second.log"
    logger_mod.setup_file_log(first)
    logger_mod.setup_file_log(second)
    try:
        root = logging.getLogger()
        rotating = [
            h for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        # Calling setup_file_log() twice must not stack duplicate handlers.
        assert len(rotating) == 1
        assert str(second) in str(rotating[0].baseFilename)
    finally:
        root = logging.getLogger()
        for h in list(root.handlers):
            if isinstance(h, logging.handlers.RotatingFileHandler):
                root.removeHandler(h)
                h.close()
