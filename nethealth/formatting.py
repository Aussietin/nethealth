"""
nethealth/formatting.py — one-line plain-text summaries of check results.

Shared by the CLI tables, the CSV history writer and anything else that needs
"what did this check say" as a short string.
"""
from __future__ import annotations


def error_of(result: dict, default: str = "failed") -> str:
    return str(result.get("error") or default)


def fmt_dns(result: dict) -> str:
    if result["status"] != "ok":
        return error_of(result)
    parts = [f"{result['latency']:.1f}ms"]
    if result.get("resolver"):
        parts.append(f"via {result['resolver']}")
    return "  ".join(parts)


def fmt_ping(result: dict) -> str:
    if result["status"] != "ok":
        return error_of(result)
    avg = result.get("avg_ms")
    return f"{avg:.1f}ms avg" if avg is not None else "ok"


def fmt_http(result: dict) -> str:
    if result["status"] != "ok":
        return error_of(result)
    method = result.get("method", "GET")
    method_tag = f"[{method}] " if method != "GET" else ""
    return f"{method_tag}HTTP {result.get('code', '?')}  ·  {result.get('latency', 0):.0f}ms"


def fmt_port(result: dict) -> str:
    if "results" not in result:
        return error_of(result)
    open_ports = [str(r["port"]) for r in result["results"] if r["status"] == "open"]
    return f"open: {', '.join(open_ports)}" if open_ports else "all closed"


def fmt_ssl(result: dict) -> str:
    if result["status"] != "ok":
        return error_of(result)
    return f"{result['days_left']}d left  ·  {result.get('tls_version') or '?'}"


def fmt_traceroute(result: dict) -> str:
    if result["status"] != "ok":
        return error_of(result)
    return f"{len(result.get('hops', []))} hops"


_FORMATTERS = {
    "dns": fmt_dns,
    "ping": fmt_ping,
    "http": fmt_http,
    "port": fmt_port,
    "ssl": fmt_ssl,
    "traceroute": fmt_traceroute,
}

LABELS = {
    "dns": "DNS",
    "ping": "Ping",
    "http": "HTTP",
    "port": "Port",
    "ssl": "SSL",
    "traceroute": "Traceroute",
}


def detail(name: str, result: dict) -> str:
    return _FORMATTERS[name](result)


def fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
