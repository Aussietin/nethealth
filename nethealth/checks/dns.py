import dns.resolver
import time


def dns_check(host):
    """
    Perform a DNS resolution check.
    
    Args:
        host (str): The hostname to resolve.
    
    Returns:
        dict: Result containing 'status', 'latency' (ms).
    """
    start = time.time()
    try:
        dns.resolver.resolve(host, "A")
        latency = (time.time() - start) * 1000
        return {"name": "DNS", "status": "ok", "latency": latency}
    except Exception as e:
        return {"name": "DNS", "status": "fail", "error": str(e)}
