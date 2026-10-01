from __future__ import annotations

import os
import socket
import struct
import subprocess
import sys
import time


def _fail(error: str) -> dict:
    return {"name": "Traceroute", "status": "fail", "error": error}


def _parse_ipv4_header(data: bytes) -> dict:
    (
        version_header_length,
        tos,
        total_length,
        identification,
        flags_fragment,
        ttl,
        protocol,
        checksum,
        src,
        dest,
    ) = struct.unpack("!BBHHHBBH4s4s", data[:20])
    header_length = (version_header_length & 0x0F) * 4
    return {
        "ttl": ttl,
        "protocol": protocol,
        "src": socket.inet_ntoa(src),
        "dest": socket.inet_ntoa(dest),
        "header_length": header_length,
        "payload": data[header_length:total_length],
    }


def _unpack_icmp_header(data: bytes) -> tuple:
    return struct.unpack("!BBH", data[:4])


def _parse_inner_udp_port(data: bytes) -> int:
    if len(data) < 8:
        return -1
    _, dest_port, _, _ = struct.unpack("!HHHH", data[:8])
    return dest_port


def _classify_icmp_reply(packet: bytes, probe_port: int) -> str | None:
    """Return the hop type if ``packet`` is the ICMP reply to *our* probe,
    else None. Offsets come from the IHL fields rather than assuming a
    20-byte IP header (IP options make it longer)."""
    icmp = _parse_ipv4_header(packet)["payload"]
    if len(icmp) < 8:
        return None
    icmp_type, icmp_code, _ = _unpack_icmp_header(icmp)
    if (icmp_type, icmp_code) not in ((11, 0), (3, 3)):
        return f"icmp_{icmp_type}_{icmp_code}"
    quoted = icmp[8:]  # original IP header + first 8 bytes of our UDP probe
    if len(quoted) < 20:
        return None
    inner_ihl = (quoted[0] & 0x0F) * 4
    if _parse_inner_udp_port(quoted[inner_ihl:inner_ihl + 8]) != probe_port:
        return None
    return "time_exceeded" if icmp_type == 11 else "destination_reached"


def _await_hop_reply(recv_socket: socket.socket, probe_port: int, timeout: float) -> dict:
    """Read ICMP replies until one answers ``probe_port`` or ``timeout`` runs
    out. Stray ICMP (another process's ping, a late reply to an earlier TTL)
    is skipped. The previous loop `continue`d to the next TTL on the first
    stray packet, silently dropping that hop from the output."""
    start = time.perf_counter()
    deadline = start + timeout
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return {"address": "*", "latency": None, "type": "timeout"}
        recv_socket.settimeout(remaining)
        try:
            packet, addr = recv_socket.recvfrom(65535)
        except socket.timeout:
            return {"address": "*", "latency": None, "type": "timeout"}
        try:
            kind = _classify_icmp_reply(packet, probe_port)
        except struct.error:
            continue
        if kind is None:
            continue
        return {
            "address": addr[0],
            "latency": round((time.perf_counter() - start) * 1000, 1),
            "type": kind,
        }


def _raw_traceroute(target: str, max_hops: int = 30, timeout: int = 2) -> dict:
    addr_info = socket.getaddrinfo(target, None, socket.AF_INET, socket.SOCK_DGRAM)
    if not addr_info:
        raise RuntimeError(f"Unable to resolve {target} to IPv4")

    dest_ip = addr_info[0][4][0]
    hops = []
    port_base = 33434

    recv_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        for ttl in range(1, max_hops + 1):
            send_socket.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl)
            probe_port = port_base + ttl
            send_socket.sendto(b"", (dest_ip, probe_port))
            hop = {"hop": ttl, **_await_hop_reply(recv_socket, probe_port, timeout)}
            hops.append(hop)
            if hop["type"] == "destination_reached":
                break
    finally:
        recv_socket.close()
        send_socket.close()

    return {
        "name": "Traceroute",
        "status": "ok",
        "method": "raw",
        "hops": hops,
        "target": target,
    }


def _parse_system_output(stdout: str) -> list[dict]:
    hops = []
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue

        hop_addr = "*"
        hop_latency = None
        for i, part in enumerate(parts):
            if part.startswith("(") and part.endswith(")"):
                hop_addr = part.strip("()")
            elif part == "ms" and i > 0:
                try:
                    hop_latency = float(parts[i - 1])
                    break
                except ValueError:
                    continue

        hops.append({"hop": int(parts[0]), "address": hop_addr, "latency": hop_latency, "type": "system"})
    return hops


def _system_traceroute(target: str, max_hops: int = 30) -> dict:
    try:
        proc = subprocess.run(
            ["traceroute", "-m", str(max_hops), "-w", "2", target],
            capture_output=True,
            text=True,
            timeout=max_hops * 2 + 5,
        )
    except subprocess.TimeoutExpired:
        return _fail("Traceroute timed out")
    except FileNotFoundError:
        return _fail("'traceroute' command not found. Install it (e.g. sudo apt install traceroute).")

    if proc.returncode != 0:
        return _fail(proc.stderr.strip() or "Traceroute failed")

    return {
        "name": "Traceroute",
        "status": "ok",
        "method": "system",
        "hops": _parse_system_output(proc.stdout),
        "target": target,
    }


def traceroute_check(target: str, max_hops: int = 30) -> dict:
    """Perform a traceroute to the target host using raw ICMP on Linux when possible."""
    if sys.platform == "linux" and os.geteuid() == 0:
        try:
            return _raw_traceroute(target, max_hops=max_hops)
        except PermissionError:
            return _system_traceroute(target, max_hops=max_hops)
        except Exception as exc:
            return _fail(str(exc))

    return _system_traceroute(target, max_hops=max_hops)
