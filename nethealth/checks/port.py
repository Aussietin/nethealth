import socket


def port_check(target, port=None, ports=None, timeout=2):
    """
    Check if a port or list of ports is open on the target host.
    
    Args:
        target (str): The hostname or IP to check.
        port (int, optional): A single port to check.
        ports (list, optional): A list of ports to check.
        timeout (int): Socket timeout in seconds.
    
    Returns:
        dict: Result containing 'status', 'results' (list of port statuses), and 'target'.
    """
    if ports is None:
        if port is not None:
            ports = [port]
        else:
            # Default common ports
            ports = [22, 80, 443]

    results = []
    for p in ports:
        try:
            with socket.create_connection((target, p), timeout=timeout):
                results.append({"port": p, "status": "open"})
        except (socket.timeout, ConnectionRefusedError, OSError):
            results.append({"port": p, "status": "closed"})

    status = "ok" if any(r["status"] == "open" for r in results) else "fail"
    
    return {
        "name": "Port",
        "status": status,
        "results": results,
        "target": target
    }
