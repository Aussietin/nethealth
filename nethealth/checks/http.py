import httpx
import time


def _request(url: str, timeout: float, method: str, headers: dict | None) -> tuple[int, float]:
    # Call httpx.get/httpx.head directly (rather than the generic
    # httpx.request) and only pass `headers` when actually set. This keeps
    # the default GET/no-headers call identical to the pre-existing
    # `httpx.get(url, timeout=timeout)` shape that the mocked unit tests in
    # test_checks_mocked.py patch onto `httpx.get` -- routing everything
    # through httpx.request silently bypassed those mocks (they only ever
    # patch httpx.get) and made the tests exercise real network calls.
    start = time.time()
    fn = httpx.head if method == "HEAD" else httpx.get
    if headers:
        r = fn(url, timeout=timeout, headers=headers)
    else:
        r = fn(url, timeout=timeout)
    latency = (time.time() - start) * 1000
    return r.status_code, latency


def http_check(host, timeout: float = 5.0, method: str = "GET", headers: dict | None = None):
    """
    Perform an HTTP/HTTPS connectivity check. Tries HTTPS first; if the
    *connection itself* fails (DNS failure, refused, TLS handshake error --
    not an HTTP-level error response, which means the connection worked
    fine) falls back to plain HTTP once. This matters for LAN gear
    (routers, printers, IoT devices) that often don't speak TLS at all --
    without the fallback they'd always show FAIL even though they're
    perfectly reachable on port 80.

    Args:
        host (str): The hostname to check.
        timeout (float): Per-attempt timeout in seconds.
        method (str): HTTP method to use — "GET" (default) or "HEAD".
            HEAD is faster for uptime checks on large resources since the
            server sends only headers.
        headers (dict | None): Optional extra request headers, e.g.
            {"Authorization": "Bearer <token>"}.

    Returns:
        dict: Result containing 'status', 'code', 'latency' (ms), and
        'scheme' (which one actually answered) on success, or 'error' on
        failure.
    """
    try:
        code, latency = _request(f"https://{host}", timeout, method, headers)
        return {
            "name": "HTTP",
            "status": "ok",
            "code": code,
            "latency": latency,
            "scheme": "https",
            "method": method,
        }
    except httpx.ConnectError as https_exc:
        try:
            code, latency = _request(f"http://{host}", timeout, method, headers)
            return {
                "name": "HTTP",
                "status": "ok",
                "code": code,
                "latency": latency,
                "scheme": "http",
                "method": method,
            }
        except Exception:
            # Neither scheme connected -- report the HTTPS failure since
            # that was the primary attempt and is usually the more
            # informative error (e.g. it'll show a TLS reason if that's
            # what actually happened, vs. plain connection-refused twice).
            return {"name": "HTTP", "status": "fail", "error": str(https_exc), "method": method}
    except Exception as e:
        return {"name": "HTTP", "status": "fail", "error": str(e), "method": method}

