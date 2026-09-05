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
# Fire a desktop notification via notify-send (Linux) or osascript (macOS).
desktop = true
# Optional generic webhook URL — leave empty to disable.
# nethealth will POST JSON: {target, check, status, error, timestamp}
webhook_url = ""
# Optional Slack Incoming Webhook URL.
slack_webhook_url = ""
# Optional Microsoft Teams Incoming Webhook URL.
teams_webhook_url = ""

[speed]
# Default download size in MB for nethealth speed.
size_mb = 10
"""

# Hard-coded fallback used when tomllib is unavailable, or the config file
# exists but fails to parse (missing/malformed handled the same way).
_HARD_DEFAULTS = {
    "defaults": {"targets": ["google.com", "1.1.1.1"], "refresh_interval": 30},
    "alerts":   {
        "enabled": True,
        "desktop": True,
        "webhook_url": "",
        "slack_webhook_url": "",
        "teams_webhook_url": "",
    },
    "speed":    {"size_mb": 10},
}


def load_with_status() -> tuple[dict, str | None]:
    """
    Return (config_dict, error_message). error_message is None unless the
    config file exists but could not be parsed, in which case hard-coded
    defaults are returned alongside a description of what went wrong —
    callers (e.g. the TUI settings screen) can surface that instead of
    crashing.
    """
    CONFIG_DIR.mkdir(exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_DEFAULT)
        return dict(_HARD_DEFAULTS), None

    if tomllib is None:
        return dict(_HARD_DEFAULTS), None

    try:
        with open(CONFIG_PATH, "rb") as fh:
            return tomllib.load(fh), None
    except Exception as exc:  # malformed TOML, permissions, encoding, etc.
        return dict(_HARD_DEFAULTS), f"{type(exc).__name__}: {exc}"


def load() -> dict:
    """Return config dict, creating the file with defaults if missing.
    Falls back to hard-coded defaults (silently) if the file is malformed."""
    data, _error = load_with_status()
    return data


def defaults() -> dict:
    return load().get("defaults", {})


def alert_cfg() -> dict:
    return load().get("alerts", {})


def save(data: dict) -> None:
    """
    Write config back to CONFIG_PATH as TOML.

    The schema is fixed (defaults/alerts/speed with known keys), so this
    re-renders the same template as _DEFAULT rather than pulling in a TOML
    writer dependency — any fields not covered by the schema are dropped,
    which is fine since the TUI settings screen is the only writer and only
    edits known fields.
    """
    defaults_ = data.get("defaults", {})
    alerts_   = data.get("alerts", {})
    speed_    = data.get("speed", {})

    targets = defaults_.get("targets") or ["google.com", "1.1.1.1"]
    targets_toml = "[" + ", ".join(f'"{t}"' for t in targets) + "]"
    refresh_interval = defaults_.get("refresh_interval", 30)
    enabled          = "true" if alerts_.get("enabled", True) else "false"
    desktop          = "true" if alerts_.get("desktop", True) else "false"
    webhook_url       = alerts_.get("webhook_url", "") or ""
    slack_webhook_url = alerts_.get("slack_webhook_url", "") or ""
    teams_webhook_url = alerts_.get("teams_webhook_url", "") or ""
    size_mb = speed_.get("size_mb", 10)

    content = f"""\
[defaults]
# Targets the TUI monitors when launched with no arguments.
targets = {targets_toml}
# Seconds between automatic check cycles in the TUI.
refresh_interval = {refresh_interval}

[alerts]
# Set to false to silence all alerts.
enabled = {enabled}
# Fire a desktop notification via notify-send (Linux) or osascript (macOS).
desktop = {desktop}
# Optional generic webhook URL — leave empty to disable.
# nethealth will POST JSON: {{target, check, status, error, timestamp}}
webhook_url = "{webhook_url}"
# Optional Slack Incoming Webhook URL.
slack_webhook_url = "{slack_webhook_url}"
# Optional Microsoft Teams Incoming Webhook URL.
teams_webhook_url = "{teams_webhook_url}"

[speed]
# Default download size in MB for nethealth speed.
size_mb = {size_mb}
"""
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(content)

