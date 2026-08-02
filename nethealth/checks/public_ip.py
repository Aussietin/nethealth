"""
nethealth/checks/public_ip.py — what's my public/external IP right now.

Useful for noticing an ISP IP change or confirming what a remote service
sees you as. Hits a public IP-echo endpoint over HTTPS -- same trust model
this codebase already has elsewhere (speed.py hits Cloudflare, ssl.py
connects to whatever host you point it at).
"""
from __future__ import annotations

import httpx

_ENDPOINT = "https://api.ipify.org?format=json"


def public_ip_check(timeout: float = 5.0) -> dict:
    """Return {"status": "ok", "ip": "..."} or {"status": "fail", "error": "..."}."""
    try:
        r = httpx.get(_ENDPOINT, timeout=timeout)
        r.raise_for_status()
        ip = r.json().get("ip")
        if not ip:
            return {"name": "PublicIP", "status": "fail", "error": "response had no 'ip' field"}
        return {"name": "PublicIP", "status": "ok", "ip": ip}
    except Exception as exc:
        return {"name": "PublicIP", "status": "fail", "error": str(exc)}
