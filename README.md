# nethealth

**nethealth** is a lightweight, extensible diagnostic tool for assessing **network health and stability**.

It performs common diagnostics — **DNS resolution**, **ICMP reachability**, **HTTP connectivity**, **TCP port checks**, **Traceroute**, and **long-running concurrent ping monitoring**.

The tool now features a **High-Performance Web Dashboard** with a **Cyberpunk Retheme**, offering real-time visual diagnostics.

The tool is designed to be:

✅ **Fast and unpredictable** (no hanging)  
✅ **Human‑readable** CLI & Web Dashboard  
✅ **Script‑friendly** and extensible  
✅ **Safe to run** without root privileges

***

## Features

### ✅ Snapshot Health Checks

*   **DNS health check**: Verifies name resolution and measures lookup latency.
*   **Ping (ICMP) check**: Uses system `ping` to report average round‑trip time.
*   **HTTP connectivity check**: HTTPS request with strict timeout.
*   **Port Reachability**: Verifies TCP port connectivity (default: 22, 80, 443).
*   **Traceroute**: Identifies network path and per-hop latency.
*   **Raw Traceroute (advanced)**: Uses TTL-based ICMP/UDP probing on Linux to map the router path directly from Python when raw sockets are available.
*   **Packet Sniffer**: Captures Ethernet frames and parses IPv4/TCP/UDP/ICMP headers on Linux using `AF_PACKET`.

### ✅ Long‑Running Monitoring

*   **Concurrent Multi‑target ping monitoring**:
    *   Monitors multiple targets simultaneously using thread pools.
    *   Timestamped logs (one per target).
    *   **Premium Shutdown**: Ctrl-C displays a session summary (Sent/Received/Loss) and closes logs cleanly.

### ✅ Web Dashboard (Live Diagnostics)

*   **Cyberpunk Aesthetics**: High-contrast Neon Lime Green theme for high readability.
*   **Real-time Monitoring**: WebSocket-driven live ping monitoring.
*   **API-First**: Built with FastAPI for high performance and low latency.
*   **Next.js Frontend**: Modern, responsive interface.

### ✅ Platform‑friendly

*   Linux & WSL friendly
*   No root / sudo required
*   Uses standard system utilities

***

## Example Usage

### Help

```bash
❯ nethealth --help
```

### Snapshot health check suite

```bash
❯ nethealth check google.com
🔎 Checking network health for google.com

✅ DNS        OK — {'name': 'DNS', 'status': 'ok', 'latency': 66.7}
✅ Ping       OK — {'name': 'Ping', 'status': 'ok', 'avg_ms': 50.6}
✅ HTTP       OK — {'name': 'HTTP', 'status': 'ok', 'code': 301, 'latency': 828.9}
✅ Port       OK — Open ports: 80, 443

🚀 Running traceroute to google.com...
✅ Traceroute complete (12 hops)
  1: 192.168.1.1 (0.9 ms)
  2: 10.0.0.1 (10.2 ms)
  3: ...
  12: 142.250.190.46 (15.4 ms)
```

### Long‑running ping monitor

```bash
nethealth monitor ping --targets google.com,1.1.1.1 --interval 1
```

Press **Ctrl‑C** at any time for a clean exit and summary:

```text
🛑 Interrupt received. Cleaning up...

--- Monitoring Summary ---
Duration: 12.5s
Target google.com    : Sent=12, Received=12, Loss=0.0%
Target 1.1.1.1       : Sent=12, Received=11, Loss=8.3%

✅ Statistics collection complete.
```

***

## Port & Traceroute Commands

You can also run individual diagnostic tools:

```bash
# Check specific ports
nethealth port google.com --ports 80,443,8080

# Detailed traceroute
nethealth traceroute google.com --max-hops 30

# Advanced Linux raw traceroute (requires root)
sudo nethealth traceroute google.com --max-hops 30

# Capture raw packets on Linux
sudo nethealth sniffer --interface any --count 8 --timeout 10
```

> Note: raw packet capture requires root privileges. If `sudo nethealth ...` reports `command not found`, the `nethealth` entrypoint is not visible in the root environment. Either install the package globally or run:
>
> ```bash
> sudo env "PATH=$PATH" nethealth sniffer --interface any --count 8 --timeout 10
> ```
>
> Or use Python directly from your project:
>
> ```bash
> sudo python -m nethealth.cli sniffer --interface any --count 8 --timeout 10
> ```

***

## Web Dashboard & Development

For developers or users who prefer a GUI, NetHealth includes a web dashboard. Use the `manage.py` script to manage the application lifecycle.

### Development Mode
Starts both the FastAPI backend (port 8000) and Next.js frontend (port 3000) with hot-reload.
```bash
python manage.py dev
```

### Build for Production
Installs dependencies and exports the frontend for static serving by the backend.
```bash
python manage.py build
```

### Run Production Server
Starts the high-performance unified server.
```bash
python manage.py run
```

***

## Project Structure

```text
nethealth/
├─ nethealth/           # Core Python Logic
│  ├─ checks/           # Diagnostic modules
│  ├─ api.py            # FastAPI backend
│  └─ cli.py            # CLI entry point
├─ frontend/            # Next.js Application (Cyberpunk UI)
├─ manage.py            # Lifecycle management script
├─ pyproject.toml       # Packaging metadata
└─ README.md            # This file
```

***

## Extending nethealth

Adding a new check is easy:

1.  Create a module in `nethealth/checks/`
2.  Define a function that returns a structured result.
3.  Import and wire it in `cli.py`

***

## License

MIT