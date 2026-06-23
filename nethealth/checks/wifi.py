import re
import subprocess


def _run(cmd: list[str], timeout: int = 5) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, p.stdout + p.stderr
    except FileNotFoundError:
        return False, ""
    except Exception as exc:
        return False, str(exc)


def _parse_iw_dev(stdout: str) -> list[str]:
    """Return list of wireless interface names from `iw dev` output."""
    return re.findall(r"Interface\s+(\S+)", stdout)


def _parse_iw_link(iface: str, stdout: str) -> dict:
    """Parse `iw dev <iface> link` output."""
    if "Not connected" in stdout:
        return {"interface": iface, "connected": False}

    result: dict = {"interface": iface, "connected": True}

    m = re.search(r"SSID:\s*(.+)", stdout)
    if m:
        result["ssid"] = m.group(1).strip()

    m = re.search(r"signal:\s*([-\d.]+)\s*dBm", stdout)
    if m:
        dbm = float(m.group(1))
        result["signal_dbm"] = dbm
        result["signal_quality"] = _dbm_to_quality(dbm)

    m = re.search(r"freq:\s*(\d+)", stdout)
    if m:
        freq_mhz = int(m.group(1))
        result["freq_mhz"] = freq_mhz
        result["band"] = "5 GHz" if freq_mhz >= 5000 else "2.4 GHz"

    m = re.search(r"tx bitrate:\s*([\d.]+)\s*MBit/s", stdout)
    if m:
        result["tx_mbps"] = float(m.group(1))

    m = re.search(r"RX:\s*(\d+)\s+bytes", stdout)
    if m:
        result["rx_bytes"] = int(m.group(1))

    return result


def _parse_iwconfig(stdout: str) -> dict | None:
    """Parse `iwconfig` output for first wireless interface."""
    # Find a block with ESSID (connected interface)
    block_re = re.compile(
        r"^(\S+)\s+IEEE 802\.11.+?(?=^\S|\Z)", re.MULTILINE | re.DOTALL
    )
    for m in block_re.finditer(stdout):
        block = m.group(0)
        iface = m.group(1)

        essid_m = re.search(r'ESSID:"([^"]*)"', block)
        if not essid_m or essid_m.group(1) in ("", "off/any"):
            continue

        result: dict = {"interface": iface, "connected": True}
        result["ssid"] = essid_m.group(1)

        sig_m = re.search(r"Signal level=([-\d]+)\s*dBm", block)
        if sig_m:
            dbm = float(sig_m.group(1))
            result["signal_dbm"] = dbm
            result["signal_quality"] = _dbm_to_quality(dbm)

        freq_m = re.search(r"Frequency:([\d.]+)\s*GHz", block)
        if freq_m:
            ghz = float(freq_m.group(1))
            result["freq_mhz"] = int(ghz * 1000)
            result["band"] = "5 GHz" if ghz >= 5 else "2.4 GHz"

        rate_m = re.search(r"Bit Rate=([\d.]+)\s*Mb/s", block)
        if rate_m:
            result["tx_mbps"] = float(rate_m.group(1))

        return result
    return None


def _dbm_to_quality(dbm: float) -> str:
    if dbm >= -50:
        return "excellent"
    if dbm >= -60:
        return "good"
    if dbm >= -70:
        return "fair"
    return "poor"


def wifi_check() -> dict:
    """
    Return WiFi connection details using iw (preferred) or iwconfig fallback.
    Returns interface, SSID, signal dBm, band, tx rate.
    Works on Linux; in WSL2 the host WiFi adapter is not exposed — will report
    the virtual interface as not connected.
    """
    # Try iw first
    ok, dev_out = _run(["iw", "dev"])
    if ok:
        ifaces = _parse_iw_dev(dev_out)
        if not ifaces:
            return {
                "name": "WiFi",
                "status": "fail",
                "error": "No wireless interfaces found (WSL2 virtual network only exposes Ethernet)",
            }
        for iface in ifaces:
            ok2, link_out = _run(["iw", "dev", iface, "link"])
            if ok2:
                info = _parse_iw_link(iface, link_out)
                if info.get("connected"):
                    return {"name": "WiFi", "status": "ok", **info}
        return {
            "name": "WiFi",
            "status": "ok",
            "interfaces": ifaces,
            "connected": False,
            "note": "Interface(s) found but not associated",
        }

    # Fallback: iwconfig
    ok, iw_out = _run(["iwconfig"])
    if ok:
        info = _parse_iwconfig(iw_out)
        if info:
            return {"name": "WiFi", "status": "ok", **info}
        return {
            "name": "WiFi",
            "status": "fail",
            "error": "iwconfig found but no connected wireless interface detected",
        }

    return {
        "name": "WiFi",
        "status": "fail",
        "error": "Neither iw nor iwconfig found. Install iw: sudo apt install iw",
    }