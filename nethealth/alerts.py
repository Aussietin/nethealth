"""
nethealth/alerts.py — fire desktop notifications and/or webhook on check failures.
Only alerts on state transition (ok/unknown → fail) to avoid spam.
"""
from __future__ import annotations

import subprocess
from datetime import datetime


def _desktop(title: str, body: str) -> None:
    try:
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