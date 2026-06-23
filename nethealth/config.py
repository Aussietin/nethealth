"""
nethealth/config.py — load ~/.nethealth/config.toml, create defaults on first run.
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            tomllib = None  # type: ignore

CONFIG_DIR  = Path.home() / ".nethealth"
CONFIG_PATH = CONFIG_DIR / "config.toml"

_DEFAULT = """\
[defaults]
# Targets the TUI monitors when launched with no arguments.
targets = ["google.com", "1.1.1.1"]
# Seconds between automatic check cycles in the TUI.
refresh_interval = 30

[alerts]
# Set to false to silence all alerts.
enabled = true
# Fire a desktop notification via notify-send (Linux).
desktop = true
# Optional webhook URL — leave empty to disable.
# nethealth will POST JSON: {target, check, status, error, timestamp}
webhook_url = ""

[speed]
# Default download size in MB for nethealth speed.
size_mb = 10
"""


def load() -> dict:
    """Return config dict, creating the file with defaults if missing."""
    CONFIG_DIR.mkdir(exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_DEFAULT)

    if tomllib is None:
        # Graceful fallback — return hard-coded defaults
        return {
            "defaults": {"targets": ["google.com", "1.1.1.1"], "refresh_interval": 30},
            "alerts":   {"enabled": True, "desktop": True, "webhook_url": ""},
            "speed":    {"size_mb": 10},
        }

    with open(CONFIG_PATH, "rb") as fh:
        return tomllib.load(fh)


def defaults() -> dict:
    return load().get("defaults", {})


def alert_cfg() -> dict:
    return load().get("alerts", {})