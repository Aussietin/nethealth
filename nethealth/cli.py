import click
import json
import csv
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from nethealth.checks.dns import dns_check
from nethealth.checks.ping import ping_check
from nethealth.checks.http import http_check
from nethealth.checks.traceroute import traceroute_check
from nethealth.checks.port import port_check
from nethealth.checks.ping_monitor import monitor_ping
from nethealth.checks.packet_sniffer import packet_sniffer_check

console = Console()


def _fmt_status(status: str) -> str:
    return "[green]✅  OK[/green]" if status == "ok" else "[red]❌  FAIL[/red]"


def _fmt_dns(result: dict) -> str:
    if result["status"] == "ok":
        return f"{result['latency']:.1f}ms"
    return result.get("error", "failed")


def _fmt_ping(result: dict) -> str:
    if result["status"] == "ok":
        avg = result.get("avg_ms")
        return f"{avg:.1f}ms avg" if avg is not None else "ok"
    return result.get("error", "failed")


def _fmt_http(result: dict) -> str:
    if result["status"] == "ok":
        return f"HTTP {result.get('code', '?')}  ·  {result.get('latency', 0):.0f}ms"
    return result.get("error", "failed")


def _fmt_port(result: dict) -> str:
    open_ports = [str(r["port"]) for r in result.get("results", []) if r["status"] == "open"]
    return f"open: {', '.join(open_ports)}" if open_ports else "all closed"


def _save_history(target: str, results: dict, fmt: str) -> Path:
    history_dir = Path.home() / ".nethealth"
    history_dir.mkdir(exist_ok=True)
    ts = datetime.now().isoformat()

    if fmt == "json":
        path = history_dir / "history.json"
        history = json.loads(path.read_text()) if path.exists() else []
        history.append({"timestamp": ts, "target": target, "results": results})
        path.write_text(json.dumps(history, indent=2))
        return path

    path = history_dir / "history.csv"
    write_header = not path.exists()
    rows = [
        {"timestamp": ts, "target": target, "check": "DNS",  "status": results["dns"]["status"],  "detail": _fmt_dns(results["dns"])},
        {"timestamp": ts, "target": target, "check": "Ping", "status": results["ping"]["status"], "detail": _fmt_ping(results["ping"])},
        {"timestamp": ts, "target": target, "check": "HTTP", "status": results["http"]["status"], "detail": _fmt_http(results["http"])},
        {"timestamp": ts, "target": target, "check": "Port", "status": results["port"]["status"], "detail": _fmt_port(results["port"])},
    ]
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "target", "check", "status", "detail"])
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    return path


@click.group()
def cli():
    """Network health diagnostics"""
    pass


@cli.command("help", hidden=True)
@click.argument("command", required=False)
@click.pass_context
def help_command(ctx, command):
    """Show help for a command."""
    if command:
        cmd = cli.get_command(ctx, command)
        if cmd is None:
            click.echo(f"Error: no such command '{command}'.")
            ctx.exit(1)
        click.echo(cmd.get_help(ctx))
    else:
        click.echo(cli.get_help(ctx))


@cli.command()
@click.argument("target")
@click.option("--skip-traceroute", is_flag=True, help="Skip the (potentially slow) traceroute check")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON (script-friendly)")
@click.option("--save", type=click.Choice(["json", "csv"]), default=None, help="Append results to ~/.nethealth/history.{json,csv}")
def check(target, skip_traceroute, output_json, save):
    """Run full network health check suite"""
    results = {
        "dns":  dns_check(target),
        "ping": ping_check(target),
        "http": http_check(target),
        "port": port_check(target),
    }
    if not skip_traceroute:
        results["traceroute"] = traceroute_check(target, max_hops=15)

    if output_json:
        click.echo(json.dumps(
            {"target": target, "timestamp": datetime.now().isoformat(), "results": results},
            indent=2,
        ))
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan", pad_edge=False)
    table.add_column("Check",  style="bold", width=14)
    table.add_column("Status", width=12)
    table.add_column("Detail", style="dim")

    check_rows = [
        ("DNS",  results["dns"],  _fmt_dns),
        ("Ping", results["ping"], _fmt_ping),
        ("HTTP", results["http"], _fmt_http),
        ("Port", results["port"], _fmt_port),
    ]
    if not skip_traceroute:
        tr = results["traceroute"]
        hop_count = len(tr.get("hops", []))
        check_rows.append(("Traceroute", tr, lambda r: f"{hop_count} hops" if r["status"] == "ok" else r.get("message", "failed")))

    passed = 0
    for name, result, fmt_fn in check_rows:
        if result["status"] == "ok":
            passed += 1
        table.add_row(name, _fmt_status(result["status"]), fmt_fn(result))

    total = len(check_rows)
    color = "green" if passed == total else ("yellow" if passed > 0 else "red")
    icon  = "✅" if passed == total else ("⚠️ " if passed > 0 else "❌")

    console.print()
    console.print(Panel(f"[bold]🔎  {target}[/bold]", expand=False))
    console.print(table)
    console.print(f"  [{color}]{icon}  {passed}/{total} checks passed[/{color}]\n")

    if save:
        path = _save_history(target, results, save)
        console.print(f"  [dim]Saved → {path}[/dim]\n")


@cli.command()
@click.argument("target")
def dns(target):
    """DNS resolution check"""
    result = dns_check(target)
    icon = "✅" if result["status"] == "ok" else "❌"
    console.print(f"{icon} [bold]DNS[/bold]  {target}  —  {_fmt_dns(result)}")


@cli.command()
@click.argument("target")
def ping(target):
    """ICMP ping check"""
    result = ping_check(target)
    icon = "✅" if result["status"] == "ok" else "❌"
    console.print(f"{icon} [bold]Ping[/bold]  {target}  —  {_fmt_ping(result)}")


@cli.command()
@click.argument("target")
def http(target):
    """HTTP/HTTPS connectivity check"""
    result = http_check(target)
    icon = "✅" if result["status"] == "ok" else "❌"
    console.print(f"{icon} [bold]HTTP[/bold]  {target}  —  {_fmt_http(result)}")


@cli.command()
@click.argument("target")
@click.option("--max-hops", default=30, help="Maximum number of hops")
def traceroute(target, max_hops):
    """Run a traceroute to a target"""
    console.print(f"\n🚀 Traceroute to [bold]{target}[/bold] ({max_hops} hops max)\n")
    result = traceroute_check(target, max_hops=max_hops)
    if result["status"] == "ok":
        table = Table(box=box.SIMPLE, show_header=True, header_style="dim", pad_edge=False)
        table.add_column("Hop",     width=4)
        table.add_column("Address", width=30)
        table.add_column("Latency", width=10)
        for hop in result["hops"]:
            latency = f"{hop['latency']} ms" if hop["latency"] is not None else "[dim]*[/dim]"
            table.add_row(str(hop["hop"]), hop["address"], latency)
        method = result.get("method", "system")
        console.print(f"[dim]method: {method}[/dim]\n")
        console.print(table)
    else:
        console.print(f"[red]❌ Fail:[/red] {result['message']}")


@cli.command()
@click.argument("target")
@click.option("--ports", default="22,80,443,8080", help="Comma-separated ports to check")
def port(target, ports):
    """Check TCP port reachability"""
    port_list = [int(p.strip()) for p in ports.split(",")]
    console.print(f"\n🔌 Checking ports [bold]{ports}[/bold] on [bold]{target}[/bold]\n")
    result = port_check(target, ports=port_list)
    for r in result["results"]:
        icon = "✅" if r["status"] == "open" else "❌"
        console.print(f"  {icon} Port [bold]{r['port']}[/bold]: {r['status'].upper()}")
    console.print()


@cli.command()
@click.option("--interface", default="any", show_default=True, help="Interface to sniff (Linux)")
@click.option("--count",     default=6,     show_default=True, type=int, help="Number of packets to capture")
@click.option("--timeout",   default=10,    show_default=True, type=int, help="Seconds to wait for packets")
def sniffer(interface, count, timeout):
    """Capture raw packets and parse Ethernet/IP/TCP/UDP/ICMP headers."""
    console.print(f"\n🕵️  Listening on [bold]{interface}[/bold] for up to [bold]{count}[/bold] packets ({timeout}s timeout)...\n")
    result = packet_sniffer_check(interface=interface, packet_count=count, timeout=timeout)
    if result["status"] != "ok":
        console.print(f"[red]❌ {result['name']} failed —[/red] {result.get('message', 'Unknown error')}")
        return

    console.print(f"[green]✅ Captured {result['packet_count']} packets from {result['interface']}[/green]\n")
    for index, packet in enumerate(result["packets"], start=1):
        eth = packet["eth"]
        console.print(f"[bold cyan]Packet {index}:[/bold cyan] {eth['src_mac']} → {eth['dest_mac']}  ether_type=0x{eth['ether_type']:04x}")
        if packet["ipv4"]:
            ip = packet["ipv4"]
            console.print(f"  [dim]IPv4[/dim]  {ip['src']} → {ip['dest']}  proto={ip['protocol']}  ttl={ip['ttl']}")
            if packet["transport"]:
                t = packet["transport"]
                if t.get("protocol") == "TCP":
                    console.print(f"  [dim]TCP[/dim]   {t['src_port']} → {t['dest_port']}  flags={t['flags']}")
                elif t.get("protocol") == "UDP":
                    console.print(f"  [dim]UDP[/dim]   {t['src_port']} → {t['dest_port']}")
                elif t.get("protocol") == "ICMP":
                    console.print(f"  [dim]ICMP[/dim]  type={t['type']}  code={t['code']}")
        else:
            console.print("  [dim]Non-IPv4 payload[/dim]")
        console.print()


@cli.group()
def monitor():
    """Long-running network monitors"""
    pass


@monitor.command("ping")
@click.option("--targets",  required=True,             help="Comma-separated hosts to monitor (e.g. 192.168.1.1,1.1.1.1,google.com)")
@click.option("--interval", default=1,   show_default=True, type=int, help="Seconds between pings")
@click.option("--duration", default=300, show_default=True, type=int, help="Total runtime in seconds")
@click.option("--log-dir",  default="nethealth-logs",  show_default=True, help="Directory to write ping logs")
def monitor_ping_cmd(targets, interval, duration, log_dir):
    """Run a long-running, multi-target ping monitor and log results."""
    target_list = [t.strip() for t in targets.split(",")]
    console.print("📡 [bold]Starting ping monitor[/bold]")
    console.print(f"  Targets : [cyan]{', '.join(target_list)}[/cyan]")
    console.print(f"  Interval: {interval}s")
    console.print(f"  Duration: {duration}s")
    console.print(f"  Logs    : [dim]{log_dir}/[/dim]\n")

    completed = monitor_ping(targets=target_list, interval=interval, duration=duration, log_dir=log_dir)

    if completed:
        console.print("\n[green]✅ Statistics collection complete.[/green]")
    else:
        console.print("\n[yellow]🛑 Session ended early by user.[/yellow]")


@cli.command()
@click.argument("targets", nargs=-1, metavar="[TARGET]...")
@click.option("--interval", default=None, type=int, help="Override refresh interval (seconds)")
def tui(targets, interval):
    """Live network health monitor (Textual TUI). Defaults come from ~/.nethealth/config.toml."""
    from nethealth.tui import run_tui

    run_tui(targets=list(targets) or None, refresh_interval=interval)


@cli.command()
@click.option("--size", default=10, show_default=True, type=int, help="Download size in MB (10 or 25 recommended)")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def speed(size, output_json):
    """Download speed test via Cloudflare."""
    from nethealth.checks.speed import speed_check

    if not output_json:
        console.print(f"\n⚡ [bold]Speed test[/bold] — downloading {size} MB from Cloudflare...\n")

    result = speed_check(size_mb=size)

    if output_json:
        import json as _json
        click.echo(_json.dumps(result, indent=2))
        return

    if result["status"] == "ok":
        mbps = result["mbps"]
        latency = result.get("latency_ms")
        elapsed = result["elapsed_s"]
        color = "green" if mbps >= 50 else ("yellow" if mbps >= 10 else "red")
        console.print(f"  [{color}]⬇  {mbps:.1f} Mbps[/{color}]")
        if latency is not None:
            console.print(f"  [dim]Latency to first byte: {latency:.0f} ms[/dim]")
        console.print(f"  [dim]Downloaded {result['bytes'] / 1_000_000:.1f} MB in {elapsed:.1f} s[/dim]\n")
    else:
        console.print(f"  [red]❌ Speed test failed:[/red] {result.get('error', 'unknown error')}\n")


@cli.command()
def wifi():
    """Show WiFi interface, SSID, signal strength, and band."""
    from nethealth.checks.wifi import wifi_check

    result = wifi_check()

    if result["status"] != "ok":
        console.print(f"\n[red]❌ WiFi:[/red] {result.get('error', 'unknown error')}\n")
        return

    console.print()
    if not result.get("connected"):
        note = result.get("note", "Not connected")
        ifaces = result.get("interfaces", [])
        console.print(f"  [yellow]⚠  WiFi:[/yellow] {note}")
        if ifaces:
            console.print(f"  [dim]Interfaces: {', '.join(ifaces)}[/dim]")
        console.print()
        return

    iface = result.get("interface", "?")
    ssid = result.get("ssid", "?")
    dbm = result.get("signal_dbm")
    quality = result.get("signal_quality", "?")
    band = result.get("band", "?")
    tx = result.get("tx_mbps")

    sig_color = {"excellent": "green", "good": "green", "fair": "yellow", "poor": "red"}.get(quality, "white")

    console.print(f"  📶 [bold]{ssid}[/bold]  [dim]({iface})[/dim]")
    if dbm is not None:
        console.print(f"  Signal : [{sig_color}]{dbm:.0f} dBm — {quality}[/{sig_color}]")
    console.print(f"  Band   : {band}")
    if tx:
        console.print(f"  TX rate: {tx:.0f} Mbps")
    console.print()


@cli.command()
@click.option("--target", default=None, help="Filter by target hostname/IP")
@click.option("--last", default=None, type=int, help="Only use the last N check runs")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def report(target, last, output_json):
    """Summary report from saved check history (~/.nethealth/history.json)."""
    from nethealth.report import generate_report
    import json as _json

    data = generate_report(target=target, last=last)

    if output_json:
        click.echo(_json.dumps(data, indent=2))
        return

    if data["status"] == "empty":
        console.print(f"\n[yellow]⚠  {data['message']}[/yellow]\n")
        return

    dr = data["date_range"]
    console.print(f"\n[bold cyan]📊  nethealth report[/bold cyan]  [dim]{dr[0]} → {dr[1]}[/dim]  ({data['entries_total']} runs)\n")

    for tgt, checks in data["per_target"].items():
        console.print(f"[bold]{tgt}[/bold]")
        table = Table(box=box.SIMPLE, show_header=True, header_style="dim", pad_edge=False)
        table.add_column("Check",   width=8)
        table.add_column("Pass%",   width=7)
        table.add_column("Avg ms",  width=9)
        table.add_column("Min ms",  width=9)
        table.add_column("Max ms",  width=9)

        for check_name, stats in checks.items():
            pct = stats["pass_pct"]
            pct_color = "green" if pct == 100 else ("yellow" if pct >= 80 else "red")
            avg = str(stats.get("avg_ms") or stats.get("avg_latency_ms") or "—")
            mn  = str(stats.get("min_ms") or stats.get("min_latency_ms") or "—")
            mx  = str(stats.get("max_ms") or stats.get("max_latency_ms") or "—")
            table.add_row(
                check_name.upper(),
                f"[{pct_color}]{pct}%[/{pct_color}]",
                avg, mn, mx,
            )
        console.print(table)
        console.print()
