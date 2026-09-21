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
EXTENDED_PORTS = DEFAULT_PORTS + [25, 53, 110, 143, 587, 993, 995, 8080, 8443, 8888, 9090, 10000]

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
    25: ("warn", "SMTP service is reachable", "Confirm it is not an open relay and accepts mail only from intended networks or authenticated users."),
    53: ("info", "DNS service is reachable", "DNS can be intentional; public recursive resolvers need rate limiting and abuse protections."),
    110: ("warn", "POP3 service is reachable", "Use POP3S (port 995) or disable legacy mail retrieval where possible."),
    143: ("warn", "IMAP service is reachable", "Use IMAPS (port 993) or require STARTTLS; credentials should never traverse the network in clear text."),
    587: ("info", "Mail submission service is reachable", "This is normal for a mail server, but it should require authentication and TLS."),
    993: ("info", "IMAPS service is reachable", "Encrypted IMAP is expected for a mail server; restrict access to intended users and networks."),
    995: ("info", "POP3S service is reachable", "Encrypted POP3 is expected for a mail server; restrict access to intended users and networks."),
    8080: ("info", "Alternate HTTP service is reachable", "Confirm this is an intended application or reverse-proxy endpoint and is not an exposed admin interface."),
    8443: ("info", "Alternate HTTPS service is reachable", "Confirm this is an intended application or reverse-proxy endpoint and is not an exposed admin interface."),
    8888: ("warn", "Common development-service port is reachable", "Port 8888 often hosts notebook or development tools; restrict it to trusted networks and require authentication."),
    9090: ("warn", "Common monitoring-service port is reachable", "Monitoring dashboards can expose infrastructure detail; restrict them to trusted networks and require authentication."),
    10000: ("warn", "Web administration port is reachable", "Port 10000 is commonly used by administrative panels; keep it behind a VPN or trusted IP allowlist."),
}

_RECOMMENDED_HEADERS = {
    "strict-transport-security": ("HSTS header is missing", "Tell browsers to use HTTPS for future visits by setting Strict-Transport-Security."),
    "content-security-policy": ("Content Security Policy is missing", "A Content-Security-Policy helps limit the impact of injected browser content."),
    "x-content-type-options": ("MIME-sniffing protection is missing", "Set X-Content-Type-Options: nosniff."),
    "referrer-policy": ("Referrer policy is missing", "Set Referrer-Policy to reduce unnecessary URL information leakage."),
    "permissions-policy": ("Permissions policy is missing", "Set Permissions-Policy to explicitly limit browser features your site does not need."),
}

LEARNING_GUIDE = [
    {
        "topic": "Reachable ports", "meaning": "A port is a numbered door into a network service. Open means a service answered, not that it is compromised.",
        "question": "Should this service be reachable from this network, and by whom?",
    },
    {
        "topic": "TLS certificate and protocol", "meaning": "TLS encrypts the connection and the certificate proves which host you reached. Expiry or verification failures weaken trust.",
        "question": "Would a user notice if this certificate expired or was replaced by an untrusted one?",
    },
    {
        "topic": "Browser security headers", "meaning": "These are instructions a website gives a browser to constrain risky behaviour, such as loading injected scripts or being embedded in a hostile page.",
        "question": "Which headers matter depends on whether this endpoint serves a browser-facing application.",
    },
]


def _finding(severity: str, title: str, detail: str, category: str, action: str | None = None) -> dict[str, str]:
    return {
        "severity": severity, "title": title, "detail": detail, "why": detail,
        "category": category, "action": action or "Confirm this is intentional and restrict access to the smallest trusted network.",
    }


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
            findings.append(_finding("warn", title, detail, "http", "Add the header after confirming it does not break the application."))

    if not (headers.get("x-frame-options") or "frame-ancestors" in headers.get("content-security-policy", "").lower()):
        findings.append(_finding(
            "warn", "Clickjacking protection is missing",
            "Another site may be able to embed this page and trick a user into clicking it.", "http",
            "Set X-Frame-Options or a CSP frame-ancestors directive.",
        ))

    if str(response.url).startswith("http://"):
        findings.append(_finding(
            "warn", "HTTPS request ended on unencrypted HTTP",
            "A redirect to HTTP removes the transport encryption expected for a secure web session.", "http",
            "Keep the final endpoint on HTTPS and redirect HTTP requests to HTTPS instead.",
        ))
    if response.status_code >= 500:
        findings.append(_finding(
            "info", "Server returned an error response",
            f"The endpoint returned HTTP {response.status_code}; this is not a vulnerability by itself, but it can hide a broken security control.", "http",
            "Resolve the server error before relying on this header assessment.",
        ))
    if headers.get("server"):
        findings.append(_finding(
            "info", "Server software is disclosed",
            "The Server response header can reveal implementation detail to an unauthenticated visitor.", "http",
            "Consider removing version detail where your web server supports it; keep patching as the primary control.",
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
        elif tls.get("tls_version") in {"TLSv1", "TLSv1.1"}:
            findings.append(_finding(
                "warn", "Legacy TLS protocol negotiated",
                f"The endpoint negotiated {tls.get('tls_version')}, which is obsolete and lacks modern protections.", "tls",
                "Require TLS 1.2 or newer on the service and retest clients before disabling legacy support.",
            ))

        headers = http_security_headers_check(target, timeout=max(timeout, 5))
        findings.extend(headers.get("findings", []))

    severity = "warn" if any(item["severity"] == "warn" for item in findings) else "ok"
    summary = {level: sum(item["severity"] == level for item in findings) for level in ("warn", "info")}
    return {
        "name": "Security", "target": target, "status": severity,
        "ports": port_result["results"], "tls": tls, "headers": headers,
        "findings": findings, "summary": summary,
    }
