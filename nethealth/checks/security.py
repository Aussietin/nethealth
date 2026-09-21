"""Read-only, defensive checks for common network exposure risks."""
from __future__ import annotations

from typing import Any

import httpx

from nethealth.checks.port import port_check
from nethealth.checks.ssl import ssl_check


# These are deliberately a small, defensive baseline rather than a port
# scanner. An open service is not automatically a vulnerability; the audit
# reports services that deserve an explicit firewall/access-control decision.
DEFAULT_PORTS = [21, 22, 23, 80, 443, 445, 3389, 5900, 3306, 5432, 6379, 27017, 9200]

_EXPOSED_SERVICE_INFO = {
    21: ("warn", "FTP service is reachable", "FTP commonly carries credentials without modern transport protection; disable it or use SFTP."),
    22: ("info", "SSH service is reachable", "Confirm it uses key-based access and is restricted to trusted networks or VPN users."),
    23: ("warn", "Telnet service is reachable", "Telnet sends credentials and session data in clear text. Disable it and use SSH instead."),
    445: ("warn", "SMB file sharing is reachable", "Keep SMB off untrusted networks and restrict it with a firewall and authenticated shares."),
    3389: ("warn", "Remote Desktop is reachable", "Restrict RDP behind a VPN or trusted IP allowlist and require MFA where available."),
    5900: ("warn", "VNC service is reachable", "Restrict VNC behind a VPN or trusted IP allowlist; do not expose it directly to the internet."),
    3306: ("warn", "MySQL service is reachable", "Databases should normally be reachable only from application hosts on a private network."),
    5432: ("warn", "PostgreSQL service is reachable", "Databases should normally be reachable only from application hosts on a private network."),
    6379: ("warn", "Redis service is reachable", "Redis should not be exposed to untrusted networks; bind it privately and require authentication."),
    27017: ("warn", "MongoDB service is reachable", "MongoDB should not be exposed to untrusted networks; bind it privately and require authentication."),
    9200: ("warn", "Elasticsearch service is reachable", "Elasticsearch should normally be private and protected by authentication and network controls."),
}

_RECOMMENDED_HEADERS = {
    "strict-transport-security": ("HSTS header is missing", "Tell browsers to use HTTPS for future visits by setting Strict-Transport-Security."),
    "content-security-policy": ("Content Security Policy is missing", "A Content-Security-Policy helps limit the impact of injected browser content."),
    "x-content-type-options": ("MIME-sniffing protection is missing", "Set X-Content-Type-Options: nosniff."),
    "referrer-policy": ("Referrer policy is missing", "Set Referrer-Policy to reduce unnecessary URL information leakage."),
}


def _finding(severity: str, title: str, detail: str, category: str) -> dict[str, str]:
    return {"severity": severity, "title": title, "detail": detail, "category": category}


def http_security_headers_check(host: str, timeout: float = 5.0) -> dict[str, Any]:
    """Inspect response headers from HTTPS without sending credentials or body data."""
    try:
        response = httpx.head(f"https://{host}", timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        return {"name": "HTTPHeaders", "status": "unavailable", "error": str(exc), "findings": []}

    headers = {key.lower(): value for key, value in response.headers.items()}
    findings: list[dict[str, str]] = []
    for header, (title, detail) in _RECOMMENDED_HEADERS.items():
        if not headers.get(header):
            findings.append(_finding("warn", title, detail, "http"))

    if not (headers.get("x-frame-options") or "frame-ancestors" in headers.get("content-security-policy", "").lower()):
        findings.append(_finding(
            "warn", "Clickjacking protection is missing",
            "Set X-Frame-Options or a CSP frame-ancestors directive.", "http",
        ))

    return {
        "name": "HTTPHeaders", "status": "ok", "url": str(response.url),
        "code": response.status_code, "headers_checked": sorted(_RECOMMENDED_HEADERS),
        "findings": findings,
    }


def security_audit(target: str, ports: list[int] | None = None, timeout: int = 2) -> dict[str, Any]:
    """Run a small read-only exposure audit against a host you are authorised to assess."""
    checked_ports = ports or DEFAULT_PORTS
    port_result = port_check(target, ports=checked_ports, timeout=timeout)
    open_ports = [item["port"] for item in port_result["results"] if item["status"] == "open"]
    findings: list[dict[str, str]] = []

    for port in open_ports:
        if port in _EXPOSED_SERVICE_INFO:
            severity, title, detail = _EXPOSED_SERVICE_INFO[port]
            findings.append(_finding(severity, title, detail, "exposure"))

    tls: dict[str, Any] | None = None
    headers: dict[str, Any] | None = None
    if 443 in open_ports:
        tls = ssl_check(target, port=443, timeout=max(timeout, 5))
        if tls["status"] != "ok":
            findings.append(_finding("warn", "TLS certificate check failed", tls.get("error", "The TLS endpoint could not be verified."), "tls"))
        elif tls.get("days_left", 0) <= 30:
            findings.append(_finding("warn", "TLS certificate expires soon", f"The certificate expires in {tls.get('days_left')} days.", "tls"))

        headers = http_security_headers_check(target, timeout=max(timeout, 5))
        findings.extend(headers.get("findings", []))

    severity = "warn" if any(item["severity"] == "warn" for item in findings) else "ok"
    return {
        "name": "Security", "target": target, "status": severity,
        "ports": port_result["results"], "tls": tls, "headers": headers,
        "findings": findings,
    }
