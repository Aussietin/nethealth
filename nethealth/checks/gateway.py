"""
nethealth/checks/gateway.py — find and ping the default gateway.

This is a system-level check, not a per-target one: it answers "am I on
the network at all" before DNS/HTTP/etc even get involved, which is the
actual first troubleshooting step for "the internet is broken" in
practice. Deliberately Linux-only (parses `ip route show default`),
matching the rest of this codebase's WSL/Linux-only posture (ping.py,
wifi.py, traceroute.py's system path are all the same).
"""
from __future__ import annotations

import re
import subprocess

from nethealth.checks.ping import ping_check


def _default_gateway_linux() -> str | None:
    """Parse `ip route show default` for the gateway IP. Returns None if
    the command is missing, times out, or there's no default route (e.g.
    no network connection at all)."""
    try:
        proc = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if proc.returncode != 0:
        return None

    match = re.search(r"default via (\S+)", proc.stdout)
    return match.group(1) if match else None


def gateway_check() -> dict:
    """Find the default gateway and ping it once (3 probes, ~3s worst
    case -- same underlying ping_check() every other check reuses)."""
    gateway = _default_gateway_linux()
    if not gateway:
        return {
            "name": "Gateway",
            "status": "fail",
            "error": "Could not determine default gateway (no default route via `ip route`).",
        }

    ping_result = ping_check(gateway)
    if ping_result["status"] != "ok":
        return {
            "name": "Gateway",
            "status": "fail",
            "gateway": gateway,
            "error": ping_result.get("error", "gateway unreachable"),
        }

    return {
        "name": "Gateway",
        "status": "ok",
        "gateway": gateway,
        "avg_ms": ping_result.get("avg_ms"),
    }
