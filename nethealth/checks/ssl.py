import ssl
import socket
from datetime import datetime, timezone


def ssl_check(host: str, port: int = 443, timeout: int = 10) -> dict:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()

        expiry = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_left = (expiry - datetime.now(timezone.utc)).days

        subject = dict(x[0] for x in cert.get("subject", []))
        issuer  = dict(x[0] for x in cert.get("issuer", []))
        sans    = [v for t, v in cert.get("subjectAltName", []) if t == "DNS"]

        return {
            "name": "SSL",
            "status": "ok" if days_left > 0 else "fail",
            "host": host,
            "port": port,
            "days_left": days_left,
            "expires": expiry.strftime("%Y-%m-%d"),
            "subject_cn": subject.get("commonName", host),
            "issuer_o": issuer.get("organizationName", "unknown"),
            "sans": sans[:5],
        }
    except ssl.SSLCertVerificationError as e:
        return {"name": "SSL", "status": "fail", "host": host, "port": port, "error": f"Verification failed: {e}"}
    except ssl.SSLError as e:
        return {"name": "SSL", "status": "fail", "host": host, "port": port, "error": f"SSL error: {e}"}
    except OSError as e:
        return {"name": "SSL", "status": "fail", "host": host, "port": port, "error": f"Connection failed: {e}"}
    except Exception as e:
        return {"name": "SSL", "status": "fail", "host": host, "port": port, "error": str(e)}
