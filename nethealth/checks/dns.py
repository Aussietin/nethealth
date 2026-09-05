from __future__ import annotations

import time

import dns.resolver


def dns_check(host: str, resolver_addr: str | None = None) -> dict:
    """
    Perform a DNS resolution check.

    Args:
        host (str): The hostname to resolve.
        resolver_addr (str | None): Optional IP address of a specific DNS
            server to query (e.g. "8.8.8.8"). Defaults to the system resolver.

    Returns:
        dict: Result containing 'status', 'latency' (ms), and optionally
        'resolver' when a custom server was specified.
    """
    start = time.time()
    try:
        if resolver_addr:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [resolver_addr]
            resolver.resolve(host, "A")
        else:
            dns.resolver.resolve(host, "A")
        latency = (time.time() - start) * 1000
        result: dict = {"name": "DNS", "status": "ok", "latency": latency}
        if resolver_addr:
            result["resolver"] = resolver_addr
        return result
    except Exception as e:
        result = {"name": "DNS", "status": "fail", "error": str(e)}
        if resolver_addr:
            result["resolver"] = resolver_addr
        return result
