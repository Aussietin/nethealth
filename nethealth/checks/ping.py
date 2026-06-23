import subprocess
import re


def ping_check(host):
    """
    Run a bounded ICMP ping using the system ping command.
    Safe for WSL (no raw sockets).
    
    Args:
        host (str): The hostname or IP to ping.
    
    Returns:
        dict: Result containing 'status' and 'avg_ms'.
    """
    try:
        proc = subprocess.run(
            ["ping", "-c", "3", "-w", "3", host],
            capture_output=True,
            text=True,
            timeout=4,
        )

        if proc.returncode != 0:
            error_msg = proc.stderr.strip() or "Ping failed"
            if "not found" in error_msg or "No such file" in error_msg:
                error_msg = "CRITICAL: 'ping' utility not installed on host system."
            elif "not permitted" in error_msg.lower():
                error_msg = "ERROR: Permission denied. Ensure user has ICMP socket capability."
            raise RuntimeError(error_msg)

        match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", proc.stdout)
        avg_ms = float(match.group(1)) if match else None

        return {
            "name": "Ping",
            "status": "ok",
            "avg_ms": avg_ms,
        }

    except FileNotFoundError:
        return {
            "name": "Ping",
            "status": "fail",
            "error": "CRITICAL: 'ping' command not found in system PATH. Is it installed?",
        }
    except Exception as e:
        return {
            "name": "Ping",
            "status": "fail",
            "error": str(e),
        }
