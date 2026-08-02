import httpx
import time


def _get(url: str, timeout: float) -> tuple[int, float]:
    start = time.time()
    r = httpx.get(url, timeout=timeout)
    latency = (time.time() - start) * 1000
    return r.status_code, latency


def http_check(host, timeout: float = 5.0):
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

    Returns:
        dict: Result containing 'status', 'code', 'latency' (ms), and
        'scheme' (which one actually answered) on success, or 'error' on
        failure.
    """
    try:
        code, latency = _get(f"https://{host}", timeout)
        return {
            "name": "HTTP",
            "status": "ok",
            "code": code,
            "latency": latency,
            "scheme": "https",
        }
    except httpx.ConnectError as https_exc:
        try:
            code, latency = _get(f"http://{host}", timeout)
            return {
                "name": "HTTP",
                "status": "ok",
                "code": code,
                "latency": latency,
                "scheme": "http",
            }
        except Exception:
            # Neither scheme connected -- report the HTTPS failure since
            # that was the primary attempt and is usually the more
            # informative error (e.g. it'll show a TLS reason if that's
            # what actually happened, vs. plain connection-refused twice).
            return {"name": "HTTP", "status": "fail", "error": str(https_exc)}
    except Exception as e:
        return {"name": "HTTP", "status": "fail", "error": str(e)}
