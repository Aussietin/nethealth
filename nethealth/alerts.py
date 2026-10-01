"""
nethealth/alerts.py — fire desktop notifications and/or webhook on check failures.
Only alerts on state transition (ok/unknown → fail) to avoid spam.

Supported channels (all opt-in via config.toml):
  desktop          — notify-send (Linux) / osascript (macOS)
  webhook_url      — generic HTTP POST with a JSON payload
  slack_webhook_url — Slack Incoming Webhook (formatted message)
  teams_webhook_url — Microsoft Teams Incoming Webhook (MessageCard)

Every channel is best-effort: an alert that can't be delivered is dropped,
never raised into the monitor loop that fired it.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime

import httpx

# The text is passed as argv, never spliced into the AppleScript source -- the
# old f-string version broke (or ran whatever followed) on an error message
# containing a double quote.
_OSASCRIPT = [
    "osascript",
    "-e", "on run argv",
    "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
    "-e", "end run",
]


def _desktop(title: str, body: str) -> None:
    if sys.platform == "darwin":
        cmd = [*_OSASCRIPT, title, body]
    else:
        cmd = ["notify-send", "--urgency=critical", "--app-name=nethealth", title, body]
    try:
        subprocess.run(cmd, timeout=3, capture_output=True)
    except Exception:
        pass


def _post(url: str, body: dict) -> None:
    try:
        httpx.post(url, json=body, timeout=5)
    except Exception:
        pass


def _slack_body(payload: dict) -> dict:
    return {"text": (
        f"🔴 *nethealth alert* — `{payload['check'].upper()}` failed\n"
        f"*Target:* `{payload['target']}`\n"
        f"*Error:* {payload['error']}\n"
        f"*Time:* {payload['timestamp']}"
    )}


def _teams_body(payload: dict) -> dict:
    check = payload["check"].upper()
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "FF0000",
        "summary": f"nethealth — {check} FAIL on {payload['target']}",
        "sections": [
            {
                "activityTitle": f"🔴 nethealth — {check} FAIL",
                "activitySubtitle": payload["target"],
                "facts": [
                    {"name": "Check",     "value": check},
                    {"name": "Target",    "value": payload["target"]},
                    {"name": "Error",     "value": payload["error"]},
                    {"name": "Timestamp", "value": payload["timestamp"]},
                ],
                "markdown": True,
            }
        ],
    }


# config key → body builder for each webhook channel
_WEBHOOKS = {
    "webhook_url": lambda payload: payload,
    "slack_webhook_url": _slack_body,
    "teams_webhook_url": _teams_body,
}


def fire(target: str, check: str, error: str, cfg: dict) -> None:
    """
    Send an alert for a failed check.
    cfg is the [alerts] section of config.toml.
    """
    if not cfg.get("enabled", True):
        return

    payload = {
        "target":    target,
        "check":     check,
        "status":    "fail",
        "error":     error,
        "timestamp": datetime.now().isoformat(),
    }

    if cfg.get("desktop", True):
        _desktop(f"nethealth — {check.upper()} FAIL", f"{target}: {error}")

    for key, build in _WEBHOOKS.items():
        if url := cfg.get(key, ""):
            _post(url, build(payload))
