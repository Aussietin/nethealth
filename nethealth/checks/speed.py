import httpx
import time

_TEST_SIZES = [
    ("10 MB",  "https://speed.cloudflare.com/__down?bytes=10000000"),
    ("25 MB",  "https://speed.cloudflare.com/__down?bytes=25000000"),
]


def speed_check(size_mb: int = 10, timeout: int = 30) -> dict:
    """
    Measure download speed by streaming from Cloudflare speed test endpoint.
    Returns mbps, latency to first byte, bytes downloaded, elapsed time.
    """
    url = f"https://speed.cloudflare.com/__down?bytes={size_mb * 1_000_000}"
    try:
        t_start = time.perf_counter()
        bytes_dl = 0
        t_first_byte = None

        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes(chunk_size=65_536):
                if t_first_byte is None:
                    t_first_byte = time.perf_counter()
                bytes_dl += len(chunk)

        elapsed = time.perf_counter() - t_start
        latency_ms = (t_first_byte - t_start) * 1000 if t_first_byte else None
        mbps = (bytes_dl * 8) / (elapsed * 1_000_000)

        return {
            "name": "Speed",
            "status": "ok",
            "mbps": mbps,
            "bytes": bytes_dl,
            "elapsed_s": elapsed,
            "latency_ms": latency_ms,
            "size_mb": size_mb,
        }

    except Exception as exc:
        return {"name": "Speed", "status": "fail", "error": str(exc)}