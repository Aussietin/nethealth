"""
nethealth/alerts.py — fire desktop notifications and/or webhook on check failures.
Only alerts on state transition (ok/unknown → fail) to avoid spam.

Supported channels (all opt-in via config.toml):
  desktop          — notify-send (Linux) / osascript (macOS)
  webhook_url      — generic HTTP POST with a JSON payload
  slack_webhook_url — Slack Incoming Webhook (formatted message)
  teams_webhook_url — Microsoft Teams Incoming Webhook (MessageCard)
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime


def _desktop(title: str, body: str) -> None:
    try:
        if sys.platform == "darwin":
            script = f'display notification "{body}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], timeout=3, capture_output=True)
        else:
            subprocess.run(
                ["notify-send", "--urgency=critical", "--app-name=nethealth", title, body],
                timeout=3,
                capture_output=True,
            )
    except Exception:
        pass


def _webhook(url: str, payload: dict) -> None:
    if not url:
        return
    try:
        import httpx
        httpx.post(url, json=payload, timeout=5)
    except Exception:
        pass


def _slack(url: str, payload: dict) -> None:
    """Post a Slack Incoming Webhook message."""
    if not url:
        return
    try:
        import httpx
        icon = "🔴" if payload["status"] == "fail" else "✅"
        text = (
            f"{icon} *nethealth alert* — `{payload['check'].upper()}` failed\n"
            f"*Target:* `{payload['target']}`\n"
            f"*Error:* {payload['error']}\n"
            f"*Time:* {payload['timestamp']}"
        )
        httpx.post(url, json={"text": text}, timeout=5)
    except Exception:
        pass


def _teams(url: str, payload: dict) -> None:
    """Post a Microsoft Teams Incoming Webhook MessageCard."""
    if not url:
        return
    try:
        import httpx
        card = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": "FF0000",
            "summary": f"nethealth — {payload['check'].upper()} FAIL on {payload['target']}",
            "sections": [
                {
                    "activityTitle": f"🔴 nethealth — {payload['check'].upper()} FAIL",
                    "activitySubtitle": payload["target"],
                    "facts": [
                        {"name": "Check",     "value": payload["check"].upper()},
                        {"name": "Target",    "value": payload["target"]},
                        {"name": "Error",     "value": payload["error"]},
                        {"name": "Timestamp", "value": payload["timestamp"]},
                    ],
                    "markdown": True,
                }
            ],
        }
        httpx.post(url, json=card, timeout=5)
    except Exception:
        pass


def fire(target: str, check: str, error: str, cfg: dict) -> None:
    """
    Send an alert for a failed check.
    cfg is the [alerts] section of config.toml.
    """
    if not cfg.get("enabled", True):
        return

    title   = f"nethealth — {check.upper()} FAIL"
    body    = f"{target}: {error}"
    payload = {
        "target":    target,
        "check":     check,
        "status":    "fail",
        "error":     error,
        "timestamp": datetime.now().isoformat(),
    }

    if cfg.get("desktop", True):
        _desktop(title, body)

    if url := cfg.get("webhook_url", ""):
        _webhook(url, payload)

    if url := cfg.get("slack_webhook_url", ""):
        _slack(url, payload)

    if url := cfg.get("teams_webhook_url", ""):
        _teams(url, payload)