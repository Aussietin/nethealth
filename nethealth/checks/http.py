import httpx
import time

def http_check(host):
    """
    Perform an HTTP/HTTPS connectivity check.
    
    Args:
        host (str): The hostname to check.
    
    Returns:
        dict: Result containing 'status', 'latency' (ms), and 'code'.
    """
    url = f"https://{host}"
    try:
        start = time.time()
        r = httpx.get(url, timeout=5.0)
        latency = (time.time() - start) * 1000
        return {
            "name": "HTTP",
            "status": "ok",
            "code": r.status_code,
            "latency": latency
        }
    except Exception as e:
        return {
            "name": "HTTP",
            "status": "fail",
            "error": str(e)
        }