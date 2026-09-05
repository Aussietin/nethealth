"""
nethealth/logger.py — optional rotating file logger.

Activated via `nethealth --log <path> <subcommand>`.  All other code that
wants to emit log records just calls `get_logger(__name__)` — if the file
handler was never configured the messages are silently discarded (root
logger level stays at WARNING unless setup_file_log() is called).
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_file_log(
    path: str | Path,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,   # 5 MB per file
    backup_count: int = 3,               # keep .1 .2 .3 rotations
) -> None:
    """Configure a RotatingFileHandler on the root logger.

    Safe to call multiple times — subsequent calls replace the previous
    handler so the log path can be overridden without stacking duplicates.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()

    # Remove any existing nethealth file handlers to avoid duplication.
    for h in list(root.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler):
            root.removeHandler(h)
            h.close()

    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    root.setLevel(level)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  Records are only emitted if setup_file_log()
    has been called; otherwise they are silently dropped by the root logger's
    default WARNING level."""
    return logging.getLogger(name)
