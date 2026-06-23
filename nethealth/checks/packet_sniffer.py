import os
import select
import socket
import struct
import time


def _format_mac(raw_bytes: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw_bytes)


def _format_ipv4(raw_bytes: bytes) -> str:
    return ".".join(str(b) for b in raw_bytes)


def _parse_ethernet_frame(packet: bytes) -> dict:
    if len(packet) < 14:
        raise ValueError("Packet too short for Ethernet header")

    dest_mac, src_mac, ether_type = struct.unpack("!6s6sH", packet[:14])
    return {
        "dest_mac": _format_mac(dest_mac),
        "src_mac": _format_mac(src_mac),
        "ether_type": ether_type,
        "payload": packet[14:],
    }


def _parse_ipv4_header(packet: bytes) -> dict:
    if len(packet) < 20:
        raise ValueError("Packet too short for IPv4 header")

    (
        version_header_length,
        tos,
        total_length,
        identification,
        flags_fragment,
        ttl,
        protocol,
        header_checksum,
        src,
        dest,
    ) = struct.unpack("!BBHHHBBH4s4s", packet[:20])
    header_length = (version_header_length & 0x0F) * 4

    return {
        "version": version_header_length >> 4,
        "header_length": header_length,
        "tos": tos,
        "total_length": total_length,
        "ttl": ttl,
        "protocol": protocol,
        "src": _format_ipv4(src),
        "dest": _format_ipv4(dest),
        "payload": packet[header_length:total_length],
    }


def _parse_tcp_header(packet: bytes) -> dict:
    if len(packet) < 20:
        return {}

    (
        src_port,
        dest_port,
        sequence,
        acknowledgement,
        offset_reserved_flags,
        window,
        checksum,
        urgent_pointer,
    ) = struct.unpack("!HHLLHHHH", packet[:20])
    data_offset = (offset_reserved_flags >> 12) * 4
    flags = offset_reserved_flags & 0x01FF

    return {
        "protocol": "TCP",
        "src_port": src_port,
        "dest_port": dest_port,
        "sequence": sequence,
        "acknowledgement": acknowledgement,
        "data_offset": data_offset,
        "flags": flags,
        "window": window,
        "checksum": checksum,
        "urgent_pointer": urgent_pointer,
    }


def _parse_udp_header(packet: bytes) -> dict:
    if len(packet) < 8:
        return {}

    src_port, dest_port, length, checksum = struct.unpack("!HHHH", packet[:8])
    return {
        "protocol": "UDP",
        "src_port": src_port,
        "dest_port": dest_port,
        "length": length,
        "checksum": checksum,
    }


def _parse_icmp_header(packet: bytes) -> dict:
    if len(packet) < 4:
        return {}

    icmp_type, code, checksum = struct.unpack("!BBH", packet[:4])
    return {
        "protocol": "ICMP",
        "type": icmp_type,
        "code": code,
        "checksum": checksum,
    }


def packet_sniffer_check(
    interface: str = "any", packet_count: int = 6, timeout: int = 10
) -> dict:
    """Capture raw packets from a Linux interface and parse Ethernet/IP/TCP/UDP/ICMP headers."""
    if os.name != "posix" or not hasattr(socket, "AF_PACKET"):
        return {
            "name": "PacketSniffer",
            "status": "fail",
            "message": "Packet sniffing requires Linux and AF_PACKET support.",
        }

    packet_count = max(1, packet_count)
    interface = interface.strip() if interface else "any"
    packets = []

    try:
        raw_socket = socket.socket(
            socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003)
        )
        if interface.lower() != "any":
            raw_socket.bind((interface, 0))
        raw_socket.setblocking(False)
    except PermissionError as exc:
        return {
            "name": "PacketSniffer",
            "status": "fail",
            "message": "Permission denied. Packet sniffing requires root privileges.",
            "error": str(exc),
        }
    except OSError as exc:
        return {
            "name": "PacketSniffer",
            "status": "fail",
            "message": f"Unable to open raw socket on interface '{interface}'.",
            "error": str(exc),
        }

    end_time = time.time() + timeout

    try:
        while len(packets) < packet_count and time.time() < end_time:
            remaining = max(0.0, end_time - time.time())
            ready, _, _ = select.select([raw_socket], [], [], remaining)
            if not ready:
                break

            raw_packet, _ = raw_socket.recvfrom(65535)
            try:
                eth = _parse_ethernet_frame(raw_packet)
            except ValueError:
                continue

            ipv4 = None
            transport = None
            if eth["ether_type"] == 0x0800:
                try:
                    ipv4 = _parse_ipv4_header(eth["payload"])
                except ValueError:
                    ipv4 = None

                if ipv4:
                    payload = ipv4["payload"]
                    if ipv4["protocol"] == 6:
                        transport = _parse_tcp_header(payload)
                    elif ipv4["protocol"] == 17:
                        transport = _parse_udp_header(payload)
                    elif ipv4["protocol"] == 1:
                        transport = _parse_icmp_header(payload)

            packets.append(
                {
                    "timestamp": round(time.time() * 1000, 2),
                    "eth": eth,
                    "ipv4": ipv4,
                    "transport": transport,
                }
            )
    finally:
        raw_socket.close()

    return {
        "name": "PacketSniffer",
        "status": "ok",
        "interface": interface,
        "packet_count": len(packets),
        "packets": packets,
    }
