from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor


def _check_one(target: str, p: int, timeout: int) -> dict:
    try:
        with socket.create_connection((target, p), timeout=timeout):
            return {"port": p, "status": "open"}
    except (socket.timeout, ConnectionRefusedError, OSError):
        return {"port": p, "status": "closed"}


def port_check(
    target: str,
    port: int | None = None,
    ports: list[int] | None = None,
    timeout: int = 2,
) -> dict:
    """
    Check if a port or list of ports is open on the target host. Ports are
    probed concurrently, not sequentially -- a host that silently drops
    (rather than actively refuses) a probe ties up the full `timeout` for
    that port, and checking 3 default ports one after another used to mean
    up to 3 * timeout seconds for a single call. With N ports probed in
    parallel the whole check costs roughly one timeout window.

    Args:
        target (str): The hostname or IP to check.
        port (int, optional): A single port to check.
        ports (list, optional): A list of ports to check.
        timeout (int): Socket timeout in seconds.

    Returns:
        dict: Result containing 'status', 'results' (list of port statuses,
        in the same order as `ports`), and 'target'.
    """
    if ports is None:
        if port is not None:
            ports = [port]
        else:
            # Default common ports
            ports = [22, 80, 443]

    with ThreadPoolExecutor(max_workers=max(1, len(ports))) as executor:
        results = list(executor.map(lambda p: _check_one(target, p, timeout), ports))

    status = "ok" if any(r["status"] == "open" for r in results) else "fail"

    return {
        "name": "Port",
        "status": status,
        "results": results,
        "target": target,
    }
