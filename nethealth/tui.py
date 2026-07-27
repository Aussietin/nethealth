"""
nethealth/tui.py — Textual TUI with Monitor / Log / Report tabs.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Sparkline,
    Static,
    TabbedContent,
    TabPane,
)

from nethealth import config as cfg_mod
from nethealth import alerts as alerts_mod
from nethealth.checks.dns import dns_check
from nethealth.checks.http import http_check
from nethealth.checks.ping import ping_check
from nethealth.checks.port import port_check
from nethealth.checks.ssl import ssl_check
from nethealth.checks.traceroute import traceroute_check
from nethealth.checks.wifi import wifi_check
from nethealth.report import generate_report

MAX_SPARKLINE_POINTS = 60
WIFI_REFRESH_INTERVAL = 60

_COL_TARGET  = "Target"
_COL_DNS     = "DNS"
_COL_PING    = "Ping"
_COL_HTTP    = "HTTP"
_COL_PORT    = "Port"
_COL_SSL     = "SSL"
_COL_UPDATED = "Updated"

_CHECKS = [_COL_DNS, _COL_PING, _COL_HTTP, _COL_PORT, _COL_SSL]

_WIFI_QUALITY_COLOR = {"excellent": "green", "good": "green", "fair": "yellow", "poor": "red"}


def _cell(text: str, ok: bool | None) -> Text:
    if ok is None:
        return Text(text, style="dim")
    return Text(text, style="green" if ok else "red bold")


def _render_wifi_text(result: dict) -> str:
    if result.get("status") != "ok" or result.get("connected") is False:
        msg = result.get("error") or result.get("note") or "not connected"
        return f"[dim]\U0001F4F6 WiFi: {msg}[/dim]"

    ssid = result.get("ssid", "?")
    dbm = result.get("signal_dbm")
    quality = result.get("signal_quality")
    band = result.get("band")

    parts = [f"\U0001F4F6 [bold]{ssid}[/bold]"]
    if dbm is not None:
        color = _WIFI_QUALITY_COLOR.get(quality, "white")
        parts.append(f"[{color}]{dbm:.0f} dBm · {quality}[/{color}]")
    if band:
        parts.append(f"[dim]{band}[/dim]")
    return "  ".join(parts)


class AddTargetScreen(ModalScreen):
    DEFAULT_CSS = """
    AddTargetScreen { align: center middle; }
    #dialog {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 52;
        height: 7;
    }
    #dialog Label { margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Add target (hostname or IP):")
            yield Input(placeholder="e.g. google.com or 1.1.1.1", id="target-input")
            yield Label("[dim]Enter to confirm · Escape to cancel[/dim]")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class TargetDetailScreen(ModalScreen):
    DEFAULT_CSS = """
    TargetDetailScreen { align: center middle; }
    #detail-dialog {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 80%;
        max-width: 76;
        height: 80%;
        max-height: 28;
    }
    #detail-title { margin-bottom: 1; }
    #detail-body { height: 1fr; }
    """

    BINDINGS: ClassVar[list] = [
        Binding("escape", "dismiss_screen", "Close"),
        Binding("t",      "run_traceroute", "Traceroute"),
        Binding("r",      "refresh_target", "Refresh now"),
    ]

    def __init__(self, target: str, tui: "NetHealthTUI") -> None:
        super().__init__()
        self.target = target
        self.tui = tui

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-dialog"):
            yield Label(
                f"[bold]{self.target}[/bold]  [dim](t traceroute · r refresh · esc close)[/dim]",
                id="detail-title",
            )
            yield RichLog(id="detail-body", highlight=True, markup=True, wrap=False)

    def on_mount(self) -> None:
        self._refresh_body()

    def _refresh_body(self) -> None:
        log = self.query_one("#detail-body", RichLog)
        log.clear()
        data = self.tui._latest.get(self.target)
        if not data:
            log.write("[dim]No data yet — waiting for first check cycle.[/dim]")
            return

        def line(label: str, ok: bool, text: str) -> None:
            color = "green" if ok else "red"
            log.write(f"  {label:<10} [{color}]{text}[/{color}]")

        dns_r, ping_r, http_r, port_r, ssl_r = (
            data.get(k) for k in ("dns", "ping", "http", "port", "ssl")
        )

        if dns_r:
            ok = dns_r["status"] == "ok"
            line("DNS", ok, f"{dns_r.get('latency', 0):.0f} ms" if ok else dns_r.get("error", "fail"))
        if ping_r:
            ok = ping_r["status"] == "ok"
            avg = ping_r.get("avg_ms")
            loss = data.get("loss_pct", 0.0)
            line("Ping", ok, f"{avg:.0f} ms  loss {loss:.0f}%" if (ok and avg is not None) else "fail")
        if http_r:
            ok = http_r["status"] == "ok"
            line("HTTP", ok, f"{http_r.get('code', '?')}" if ok else http_r.get("error", "fail"))
        if port_r:
            open_p = [str(x["port"]) for x in port_r.get("results", []) if x["status"] == "open"]
            line("Port", bool(open_p), ", ".join(open_p) if open_p else "none open")
        if ssl_r:
            ok = ssl_r["status"] == "ok"
            if ok:
                days = ssl_r["days_left"]
                line("SSL", days > 7, f"{ssl_r['expires']}  ({days}d)  {ssl_r['subject_cn']}  issuer {ssl_r['issuer_o']}")
            else:
                line("SSL", False, ssl_r.get("error", "fail"))

        latency = self.tui._latency.get(self.target)
        if latency:
            vals = list(latency)
            log.write("")
            log.write(
                f"  Latency    [dim]min {min(vals):.0f} · avg {sum(vals)/len(vals):.0f} · "
                f"max {max(vals):.0f} ms  ({len(vals)} samples)[/dim]"
            )

        log.write("")
        log.write("[dim]Press t to run a traceroute (may take a few seconds)[/dim]")

    def action_dismiss_screen(self) -> None:
        self.dismiss()

    def action_refresh_target(self) -> None:
        self.tui._run_checks(self.target)
        log = self.query_one("#detail-body", RichLog)
        log.write("\n[cyan]Refreshing…[/cyan]")
        self.set_timer(1.2, self._refresh_body)

    @work(thread=True)
    def action_run_traceroute(self) -> None:
        log = self.query_one("#detail-body", RichLog)
        self.app.call_from_thread(log.write, "\n[cyan]Running traceroute…[/cyan]")
        try:
            result = traceroute_check(self.target)
        except Exception as exc:
            self.app.call_from_thread(log.write, f"[red]Traceroute error: {exc}[/red]")
            return
        self.app.call_from_thread(self._write_traceroute, result)

    def _write_traceroute(self, result: dict) -> None:
        log = self.query_one("#detail-body", RichLog)
        if result.get("status") != "ok":
            log.write(f"[red]{result.get('message', 'traceroute failed')}[/red]")
            return
        for hop in result.get("hops", []):
            addr = hop.get("address", "*")
            lat = hop.get("latency")
            lat_s = f"{lat:.0f} ms" if lat is not None else "*"
            color = "dim" if addr == "*" else "white"
            log.write(f"  [{color}]{hop.get('hop'):>3}  {addr:<16} {lat_s}[/{color}]")


class NetHealthTUI(App):
    TITLE = "nethealth"
    SUB_TITLE = "Network Health Monitor"

    BINDINGS: ClassVar[list] = [
        Binding("q",   "quit",         "Quit"),
        Binding("r",   "refresh",      "Refresh"),
        Binding("t",   "add_target",   "Add target"),
        Binding("d",   "remove_target", "Remove"),
        Binding("p",   "toggle_pause", "Pause/Resume"),
        Binding("1",   "show_tab('monitor')", "Monitor",  show=False),
        Binding("2",   "show_tab('log')",     "Log",      show=False),
        Binding("3",   "show_tab('report')",  "Report",   show=False),
    ]

    DEFAULT_CSS = """
    TabbedContent, TabPane { height: 1fr; }
    #wifi-bar {
        height: 1;
        padding: 0 1;
        background: $primary-darken-3;
    }
    #monitor-pane { height: 1fr; }
    #monitor-left {
        width: 58%;
        border-right: solid $primary-darken-2;
    }
    #monitor-right { width: 42%; }
    .panel-title {
        background: $primary-darken-3;
        padding: 0 1;
        text-style: bold;
    }
    DataTable { height: 1fr; }
    #spark-scroll { height: 1fr; padding: 0 1; }
    Sparkline   { height: 5; margin-bottom: 0; }
    .spark-label { margin-top: 1; }
    #log-panel    { height: 1fr; }
    #report-panel { height: 1fr; }
    """

    def __init__(self, targets: list[str], refresh_interval: int = 30) -> None:
        super().__init__()
        self._targets:        list[str]               = list(targets)
        self._refresh:        int                     = refresh_interval
        self._paused:         bool                    = False
        self._latency:        dict[str, deque]        = defaultdict(lambda: deque(maxlen=MAX_SPARKLINE_POINTS))
        self._sparklines:     dict[str, Sparkline]    = {}
        self._spark_labels:   dict[str, Label]        = {}
        self._ping_stats:     dict[str, list[int]]    = defaultdict(lambda: [0, 0])
        # state tracking for alerts: {target: {check: "ok"|"fail"|"unknown"}}
        self._states:         dict[str, dict[str, str]] = defaultdict(lambda: defaultdict(lambda: "unknown"))
        self._latest:         dict[str, dict]         = {}
        self._alert_cfg:      dict                    = cfg_mod.alert_cfg()
        self._report_loaded:  bool                    = False

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="wifi-bar")
        with TabbedContent(initial="monitor"):
            with TabPane("  Monitor  ", id="monitor"):
                with Horizontal(id="monitor-pane"):
                    with Vertical(id="monitor-left"):
                        yield Static("  Status", classes="panel-title")
                        yield DataTable(id="status-table", cursor_type="row")
                    with Vertical(id="monitor-right"):
                        yield Static("  Ping Latency (ms)", classes="panel-title")
                        with VerticalScroll(id="spark-scroll"):
                            pass
            with TabPane("  Log  ", id="log"):
                yield RichLog(id="log-panel", highlight=True, markup=True, wrap=False)
            with TabPane("  Report  ", id="report"):
                yield RichLog(id="report-panel", highlight=True, markup=True, wrap=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for col in [_COL_TARGET, _COL_DNS, _COL_PING, _COL_HTTP, _COL_PORT, _COL_SSL, _COL_UPDATED]:
            table.add_column(col, key=col)

        for target in self._targets:
            table.add_row(
                target,
                _cell("—", None), _cell("—", None), _cell("—", None), _cell("—", None), _cell("—", None), "—",
                key=target,
            )
            self._mount_sparkline(target)

        self._log(f"[cyan]nethealth TUI[/cyan] — watching {len(self._targets)} target(s)  "
                  f"[dim]refresh every {self._refresh}s · keys: r refresh · t add · d remove · "
                  f"p pause · enter details · 1/2/3 tabs · q quit[/dim]")

        self.set_interval(self._refresh, self._auto_refresh)
        self.set_interval(WIFI_REFRESH_INTERVAL, self._refresh_wifi)
        self.action_refresh()
        self._refresh_wifi()

    # ── Sparklines ────────────────────────────────────────────────────────────

    def _mount_sparkline(self, target: str) -> None:
        scroll = self.query_one("#spark-scroll")
        label = Label(f"[dim]{target}[/dim]", classes="spark-label")
        spark = Sparkline([], summary_function=max)
        self._sparklines[target] = spark
        self._spark_labels[target] = label
        scroll.mount(label)
        scroll.mount(spark)

    # ── Tab switching ─────────────────────────────────────────────────────────

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane and event.pane.id == "report":
            self._refresh_report()

    # ── Row selection → detail screen ────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        target = event.row_key.value
        if target in self._targets:
            self.push_screen(TargetDetailScreen(target, self))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _auto_refresh(self) -> None:
        if not self._paused:
            self.action_refresh()

    def action_refresh(self) -> None:
        for target in self._targets:
            self._run_checks(target)

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        self.sub_title = "Network Health Monitor" + ("  [PAUSED]" if self._paused else "")
        state = "paused" if self._paused else "resumed"
        color = "yellow" if self._paused else "green"
        self._log(f"[{color}]Monitoring {state}[/{color}]")

    def action_add_target(self) -> None:
        def on_dismiss(result: str | None) -> None:
            if not result or result in self._targets:
                return
            self._targets.append(result)
            self.query_one(DataTable).add_row(
                result,
                _cell("—", None), _cell("—", None), _cell("—", None), _cell("—", None), _cell("—", None), "—",
                key=result,
            )
            self._latency[result]
            self._mount_sparkline(result)
            self._log(f"[green]Added target:[/green] {result}")
            self._run_checks(result)

        self.push_screen(AddTargetScreen(), on_dismiss)

    def action_remove_target(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None or not self._targets:
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        target = row_key.value
        if target not in self._targets:
            return

        table.remove_row(row_key)
        self._targets.remove(target)
        self._latency.pop(target, None)
        self._ping_stats.pop(target, None)
        self._states.pop(target, None)
        self._latest.pop(target, None)

        spark = self._sparklines.pop(target, None)
        label = self._spark_labels.pop(target, None)
        if spark is not None:
            spark.remove()
        if label is not None:
            label.remove()

        self._log(f"[red]Removed target:[/red] {target}")

    # ── WiFi bar ──────────────────────────────────────────────────────────────

    @work(thread=True)
    def _refresh_wifi(self) -> None:
        try:
            result = wifi_check()
        except Exception as exc:
            result = {"status": "fail", "error": str(exc)}
        self.call_from_thread(self._update_wifi_bar, result)

    def _update_wifi_bar(self, result: dict) -> None:
        self.query_one("#wifi-bar", Static).update(_render_wifi_text(result))

    # ── Worker ────────────────────────────────────────────────────────────────

    @work(thread=True)
    def _run_checks(self, target: str) -> None:
        try:
            dns_r  = dns_check(target)
            ping_r = ping_check(target)
            http_r = http_check(target)
            port_r = port_check(target)
            ssl_r  = ssl_check(target, timeout=5)
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Error checking {target}: {exc}[/red]")
            return

        # Fire alerts on state transitions
        results_map = {
            "dns":  dns_r,
            "ping": ping_r,
            "http": http_r,
            "port": port_r,
            "ssl":  ssl_r,
        }
        for check_name, result in results_map.items():
            new_state = result["status"]  # "ok" or "fail"
            old_state = self._states[target][check_name]
            if new_state == "fail" and old_state != "fail":
                error = result.get("error", result.get("message", "check failed"))
                alerts_mod.fire(target, check_name, str(error), self._alert_cfg)
            self._states[target][check_name] = new_state

        self.call_from_thread(self._update_ui, target, dns_r, ping_r, http_r, port_r, ssl_r)

    # ── UI update ─────────────────────────────────────────────────────────────

    def _update_ui(self, target, dns_r, ping_r, http_r, port_r, ssl_r) -> None:
        def _ok(r): return r["status"] == "ok"

        # Ping stats
        stats = self._ping_stats[target]
        stats[0] += 1
        ping_ok = _ok(ping_r)
        if ping_ok:
            stats[1] += 1
        loss_pct = (1 - stats[1] / stats[0]) * 100 if stats[0] else 0.0
        avg = ping_r.get("avg_ms")

        # Sparkline
        if ping_ok and avg is not None:
            self._latency[target].append(avg)
            spark = self._sparklines.get(target)
            if spark is not None:
                spark.data = list(self._latency[target])

        # Sparkline label
        label = self._spark_labels.get(target)
        if label is not None:
            lc = "green" if loss_pct == 0 else ("yellow" if loss_pct < 10 else "red")
            ms_part = f"  {avg:.0f} ms" if (ping_ok and avg is not None) else ""
            label.update(f"[dim]{target}[/dim]{ms_part}  [{lc}]loss {loss_pct:.0f}%[/{lc}]")

        # Cells
        dns_cell  = _cell(f"{dns_r.get('latency',0):.0f} ms",        _ok(dns_r))  if _ok(dns_r)  else _cell("FAIL", False)
        ping_cell = _cell(f"{avg:.0f} ms  loss {loss_pct:.0f}%", ping_ok) if (ping_ok and avg) else _cell("FAIL", False)
        http_cell = _cell(f"{http_r.get('code','?')}",                _ok(http_r)) if _ok(http_r) else _cell("FAIL", False)
        open_p    = [str(x["port"]) for x in port_r.get("results",[]) if x["status"]=="open"]
        port_cell = _cell(",".join(open_p), True) if open_p else _cell("closed", False)
        if _ok(ssl_r):
            days = ssl_r["days_left"]
            ssl_cell = _cell(f"{days}d", days > 7)
        else:
            ssl_cell = _cell("FAIL", False)
        now       = datetime.now().strftime("%H:%M:%S")

        table = self.query_one(DataTable)
        table.update_cell(target, _COL_DNS,     dns_cell,  update_width=True)
        table.update_cell(target, _COL_PING,    ping_cell, update_width=True)
        table.update_cell(target, _COL_HTTP,    http_cell, update_width=True)
        table.update_cell(target, _COL_PORT,    port_cell, update_width=True)
        table.update_cell(target, _COL_SSL,     ssl_cell,  update_width=True)
        table.update_cell(target, _COL_UPDATED, now,       update_width=True)

        self._latest[target] = {
            "dns": dns_r, "ping": ping_r, "http": http_r, "port": port_r, "ssl": ssl_r,
            "loss_pct": loss_pct, "avg_ms": avg,
        }

        all_ok = all(_ok(r) for r in [dns_r, ping_r, http_r, port_r])
        icons  = "".join("✓" if _ok(r) else "✗" for r in [dns_r, ping_r, http_r, port_r])
        color  = "green" if all_ok else "red"
        self._log(
            f"[{color}]{icons}[/{color}] [bold]{target}[/bold]"
            + (f"  {avg:.0f} ms" if (ping_ok and avg) else "")
            + (f"  loss {loss_pct:.0f}%" if stats[0] > 1 else "")
            + f"  [dim]{now}[/dim]"
        )

    # ── Report tab ────────────────────────────────────────────────────────────

    def _refresh_report(self) -> None:
        panel = self.query_one("#report-panel", RichLog)
        panel.clear()
        data = generate_report()

        if data["status"] == "empty":
            panel.write(f"[yellow]{data['message']}[/yellow]")
            panel.write("[dim]Run: nethealth check <target> --save json[/dim]")
            return

        dr = data["date_range"]
        panel.write(f"[bold cyan]nethealth report[/bold cyan]  [dim]{dr[0]} → {dr[1]}[/dim]  ({data['entries_total']} runs)\n")

        for tgt, checks in data["per_target"].items():
            panel.write(f"[bold]{tgt}[/bold]")
            for check_name, stats in checks.items():
                pct = stats["pass_pct"]
                pc  = "green" if pct == 100 else ("yellow" if pct >= 80 else "red")
                avg = stats.get("avg_ms") or stats.get("avg_latency_ms")
                mn  = stats.get("min_ms") or stats.get("min_latency_ms")
                mx  = stats.get("max_ms") or stats.get("max_latency_ms")
                avg_s = f"{avg} ms" if avg else "—"
                rng_s = f"[dim]{mn}–{mx} ms[/dim]" if mn and mx else ""
                panel.write(f"  {check_name.upper():<6} [{pc}]{pct}%[/{pc}]  avg {avg_s}  {rng_s}")
            panel.write("")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self.query_one("#log-panel", RichLog).write(msg)


def run_tui(targets: list[str] | None = None, refresh_interval: int | None = None) -> None:
    cfg = cfg_mod.defaults()
    t   = targets        if targets         else cfg.get("targets",          ["google.com", "1.1.1.1"])
    r   = refresh_interval if refresh_interval else cfg.get("refresh_interval", 30)
    NetHealthTUI(t, r).run()
