import os
import socket
import struct
import subprocess
import sys
import time


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


def _raw_traceroute(target: str, max_hops: int = 30, timeout: int = 2) -> dict:
    addr_info = socket.getaddrinfo(target, None, socket.AF_INET, socket.SOCK_DGRAM)
    if not addr_info:
        raise RuntimeError(f"Unable to resolve {target} to IPv4")

    dest_ip = addr_info[0][4][0]
    hops = []
    port_base = 33434

    try:
        recv_socket = socket.socket(
            socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP
        )
        recv_socket.settimeout(timeout)
    except PermissionError as exc:
        raise

    send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    try:
        for ttl in range(1, max_hops + 1):
            send_socket.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl)
            probe_port = port_base + ttl
            send_socket.sendto(b"", (dest_ip, probe_port))
            start = time.time()

            try:
                packet, addr = recv_socket.recvfrom(65535)
                elapsed_ms = round((time.time() - start) * 1000, 1)
                src_ip = addr[0]

                ip_info = _parse_ipv4_header(packet)
                icmp_type, icmp_code, _ = _unpack_icmp_header(packet[20:24])

                if icmp_type == 11 and icmp_code == 0:
                    inner_ip_header = packet[28:48]
                    inner_udp_header = packet[48:56]
                    inner_dest_port = _parse_inner_udp_port(inner_udp_header)
                    if inner_dest_port != probe_port:
                        continue
                    hops.append(
                        {
                            "hop": ttl,
                            "address": src_ip,
                            "latency": elapsed_ms,
                            "type": "time_exceeded",
                        }
                    )
                elif icmp_type == 3 and icmp_code == 3:
                    inner_ip_header = packet[28:48]
                    inner_udp_header = packet[48:56]
                    inner_dest_port = _parse_inner_udp_port(inner_udp_header)
                    if inner_dest_port != probe_port:
                        continue
                    hops.append(
                        {
                            "hop": ttl,
                            "address": src_ip,
                            "latency": elapsed_ms,
                            "type": "destination_reached",
                        }
                    )
                    break
                else:
                    hops.append(
                        {
                            "hop": ttl,
                            "address": src_ip,
                            "latency": elapsed_ms,
                            "type": f"icmp_{icmp_type}_{icmp_code}",
                        }
                    )

            except socket.timeout:
                hops.append(
                    {"hop": ttl, "address": "*", "latency": None, "type": "timeout"}
                )
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


def _system_traceroute(target: str, max_hops: int = 30) -> dict:
    try:
        proc = subprocess.run(
            ["traceroute", "-m", str(max_hops), "-w", "2", target],
            capture_output=True,
            text=True,
            timeout=max_hops * 2 + 5,
        )

        if proc.returncode != 0:
            return {
                "name": "Traceroute",
                "status": "fail",
                "message": proc.stderr.strip() or "Traceroute failed",
            }

        lines = proc.stdout.splitlines()
        hops = []
        for line in lines[1:]:
            parts = line.split()
            if not parts:
                continue

            hop_num = parts[0]
            hop_addr = "*"
            hop_latency = None

            for i, part in enumerate(parts):
                if "(" in part and ")" in part:
                    hop_addr = part.strip("()")
                elif "ms" in part and i > 0:
                    try:
                        hop_latency = float(parts[i - 1])
                        break
                    except ValueError:
                        continue

            hops.append(
                {
                    "hop": hop_num,
                    "address": hop_addr,
                    "latency": hop_latency,
                    "type": "system",
                }
            )

        return {
            "name": "Traceroute",
            "status": "ok",
            "method": "system",
            "hops": hops,
            "target": target,
        }

    except subprocess.TimeoutExpired:
        return {
            "name": "Traceroute",
            "status": "fail",
            "message": "Traceroute timed out",
        }
    except FileNotFoundError:
        return {
            "name": "Traceroute",
            "status": "fail",
            "message": "'traceroute' command not found. Install it (e.g. sudo apt install traceroute).",
        }


def traceroute_check(target: str, max_hops: int = 30) -> dict:
    """Perform a traceroute to the target host using raw ICMP on Linux when possible."""
    if sys.platform == "linux" and os.geteuid() == 0:
        try:
            return _raw_traceroute(target, max_hops=max_hops)
        except PermissionError:
            return _system_traceroute(target, max_hops=max_hops)
        except Exception as exc:
            return {
                "name": "Traceroute",
                "status": "fail",
                "message": str(exc),
            }

    return _system_traceroute(target, max_hops=max_hops)
