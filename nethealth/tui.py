"""
nethealth/tui.py — Textual TUI with Monitor / Log / Report tabs.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
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
from nethealth.checks.speed import speed_check
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


def _safe_check(fn, *args, **kwargs) -> dict:
    """Run a check_* function, converting a genuinely unexpected exception
    (as opposed to the {"status": "fail", ...} dict every check function
    already returns for its own known failure modes) into the same shape,
    so one bad check can't blank an entire refresh cycle for a target."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return {"status": "fail", "error": f"internal error: {exc}"}

_WIFI_QUALITY_COLOR = {"excellent": "green", "good": "green", "fair": "yellow", "poor": "red"}


def _cell(text: str, ok: bool | None) -> Text:
    if ok is None:
        return Text(text, style="dim")
    return Text(text, style="green" if ok else "red bold")


def _checking_cell() -> Text:
    return Text("…", style="yellow")


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


class SettingsScreen(ModalScreen):
    """View/edit ~/.nethealth/config.toml. Mirrors TargetDetailScreen's
    modal structure: a bordered dialog, its own BINDINGS, dismiss to close."""

    DEFAULT_CSS = """
    SettingsScreen { align: center middle; }
    #settings-dialog {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 64;
        height: auto;
    }
    #settings-dialog Label { margin-top: 1; }
    #settings-warning { color: $warning; margin-top: 1; }
    #settings-buttons { margin-top: 1; height: 3; align-horizontal: right; }
    #settings-buttons Button { margin-left: 1; }
    """

    BINDINGS: ClassVar[list] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        data, error = cfg_mod.load_with_status()
        defaults_ = data.get("defaults", {})
        alerts_   = data.get("alerts", {})

        with Vertical(id="settings-dialog"):
            yield Label("[bold]nethealth settings[/bold]  [dim]~/.nethealth/config.toml[/dim]")
            if error:
                yield Static(
                    f"[yellow]Config file couldn't be read ({error}) — showing defaults.\n"
                    f"Saving will replace it with a valid file.[/yellow]",
                    id="settings-warning",
                )
            yield Label("Default targets (comma-separated):")
            yield Input(
                value=", ".join(defaults_.get("targets", [])),
                placeholder="google.com, 1.1.1.1",
                id="settings-targets",
            )
            yield Label("Refresh interval (seconds):")
            yield Input(
                value=str(defaults_.get("refresh_interval", 30)),
                id="settings-interval",
            )
            yield Label("Alert webhook URL (optional):")
            yield Input(
                value=alerts_.get("webhook_url", "") or "",
                placeholder="https://…",
                id="settings-webhook",
            )
            with Horizontal(id="settings-buttons"):
                yield Button("Cancel", id="settings-cancel")
                yield Button("Save", id="settings-save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#settings-targets", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save":
            self._save()
        elif event.button.id == "settings-cancel":
            self.dismiss(None)

    def _save(self) -> None:
        targets_raw  = self.query_one("#settings-targets", Input).value
        interval_raw = self.query_one("#settings-interval", Input).value.strip()
        webhook      = self.query_one("#settings-webhook", Input).value.strip()

        targets = [t.strip() for t in targets_raw.split(",") if t.strip()]
        if not targets:
            self.app.notify("At least one default target is required", severity="error")
            return

        try:
            interval = int(interval_raw)
            if interval <= 0:
                raise ValueError
        except ValueError:
            self.app.notify(
                "Refresh interval must be a positive whole number of seconds",
                severity="error",
            )
            return

        data, _ = cfg_mod.load_with_status()
        data.setdefault("defaults", {})
        data["defaults"]["targets"] = targets
        data["defaults"]["refresh_interval"] = interval
        data.setdefault("alerts", {})
        data["alerts"]["webhook_url"] = webhook

        try:
            cfg_mod.save(data)
        except Exception as exc:
            self.app.notify(f"Could not write config file: {exc}", severity="error")
            return

        self.dismiss({"targets": targets, "refresh_interval": interval, "webhook_url": webhook})


class NetHealthTUI(App):
    TITLE = "nethealth"
    SUB_TITLE = "Network Health Monitor"

    BINDINGS: ClassVar[list] = [
        Binding("q",   "quit",         "Quit"),
        Binding("r",   "refresh",      "Refresh"),
        Binding("t",   "add_target",   "Add target"),
        Binding("d",   "remove_target", "Remove"),
        Binding("p",   "toggle_pause", "Pause/Resume"),
        Binding("s",   "run_speed_test", "Speed test"),
        Binding("slash", "toggle_filter", "Filter"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        Binding("c",   "open_settings", "Settings"),
        Binding("1",   "show_tab('monitor')", "Monitor",  show=False),
        Binding("2",   "show_tab('log')",     "Log",      show=False),
        Binding("3",   "show_tab('report')",  "Report",   show=False),
    ]

    DEFAULT_CSS = """
    TabbedContent, TabPane { height: 1fr; }
    #info-bar {
        height: 1;
        background: $primary-darken-3;
    }
    #wifi-status {
        width: 1fr;
        padding: 0 1;
    }
    #health-status {
        width: 1fr;
        padding: 0 1;
        text-align: right;
    }
    #monitor-pane { height: 1fr; }
    #filter-input {
        display: none;
        border: solid $accent;
    }
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
        self._latest_cells:   dict[str, tuple]        = {}
        self._filter:         str                     = ""
        self._alert_cfg:      dict                    = cfg_mod.alert_cfg()
        self._report_loaded:  bool                    = False

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="info-bar"):
            yield Static(id="wifi-status")
            yield Static(id="health-status")
        with TabbedContent(initial="monitor"):
            with TabPane("  Monitor  ", id="monitor"):
                with Horizontal(id="monitor-pane"):
                    with Vertical(id="monitor-left"):
                        yield Static("  Status", classes="panel-title")
                        yield Input(placeholder="Filter targets… (Esc to clear)", id="filter-input")
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
            self._mount_sparkline(target)
        self._rebuild_table()

        self._log(f"[cyan]nethealth TUI[/cyan] — watching {len(self._targets)} target(s)  "
                  f"[dim]refresh every {self._refresh}s · keys: r refresh · t add · d remove · "
                  f"p pause · s speed test · / filter · c settings · enter details · "
                  f"ctrl+p commands · 1/2/3 tabs · q quit[/dim]")

        self._update_health_bar()
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

    # ── Filter ────────────────────────────────────────────────────────────────

    def _target_matches(self, target: str) -> bool:
        return not self._filter or self._filter in target.lower()

    def _rebuild_table(self) -> None:
        """Re-render the DataTable rows from self._targets, narrowed to
        whatever matches self._filter. Uses cached cell values from the
        last check cycle (self._latest_cells) so filtering doesn't blank
        out data that's already known — background checks keep running
        for every target regardless of what's currently visible."""
        table = self.query_one(DataTable)
        table.clear()
        checking = (_checking_cell(),) * 5 + ("—",)
        for target in self._targets:
            if not self._target_matches(target):
                continue
            cells = self._latest_cells.get(target, checking)
            table.add_row(target, *cells, key=target)

    def action_toggle_filter(self) -> None:
        filt = self.query_one("#filter-input", Input)
        if filt.display:
            self.action_clear_filter()
        else:
            filt.display = True
            filt.focus()

    def action_clear_filter(self) -> None:
        filt = self.query_one("#filter-input", Input)
        if not filt.display and not self._filter:
            return
        filt.value = ""
        filt.display = False
        self._filter = ""
        self._rebuild_table()
        self.query_one(DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._filter = event.value.strip().lower()
            self._rebuild_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-input":
            self.query_one(DataTable).focus()

    # ── Settings ──────────────────────────────────────────────────────────────

    def action_open_settings(self) -> None:
        def on_dismiss(result: dict | None) -> None:
            if result is None:
                return
            # Alert config (webhook) is cheap to hot-apply immediately.
            self._alert_cfg = cfg_mod.alert_cfg()
            # Default targets / refresh interval are persisted to the config
            # file but only take effect on the *next* TUI launch — this
            # session keeps running with whatever targets/interval it
            # started with (or whatever t/d have since changed), same as
            # editing the TOML file by hand would.
            self._log(
                f"[green]Settings saved[/green] — {len(result['targets'])} default target(s), "
                f"refresh {result['refresh_interval']}s, webhook "
                f"{'set' if result['webhook_url'] else 'cleared'}"
            )
            self.notify(
                "Saved. Alert webhook applied immediately — "
                "default targets and refresh interval take effect next launch.",
                title="Settings",
                severity="information",
                timeout=6,
            )

        self.push_screen(SettingsScreen(), on_dismiss)

    # ── Row selection → detail screen ────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._open_detail_for_cursor()

    def _open_detail_for_cursor(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None or not self._targets:
            self.notify("No target selected", severity="warning")
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        target = row_key.value
        if target in self._targets:
            self.push_screen(TargetDetailScreen(target, self))

    # ── Command palette ───────────────────────────────────────────────────────

    def get_system_commands(self, screen: Screen):
        yield from super().get_system_commands(screen)
        yield SystemCommand("Add target", "Monitor a new host or IP", self.action_add_target)
        yield SystemCommand("Remove selected target", "Stop monitoring the highlighted row", self.action_remove_target)
        yield SystemCommand(
            "Resume monitoring" if self._paused else "Pause monitoring",
            "Toggle the automatic refresh loop",
            self.action_toggle_pause,
        )
        yield SystemCommand("Refresh now", "Run all checks immediately", self.action_refresh)
        yield SystemCommand("Run speed test", "Measure download speed via Cloudflare", self.action_run_speed_test)
        yield SystemCommand("View target details", "Open the detail view for the highlighted row", self._open_detail_for_cursor)
        yield SystemCommand("Filter targets", "Narrow the Monitor table to matching targets", self.action_toggle_filter)
        if self._filter:
            yield SystemCommand("Clear filter", "Show all targets in the Monitor table", self.action_clear_filter)
        yield SystemCommand("Settings", "View and edit ~/.nethealth/config.toml", self.action_open_settings)
        yield SystemCommand("Monitor tab", "Switch to the Monitor tab", lambda: self.action_show_tab("monitor"))
        yield SystemCommand("Log tab", "Switch to the Log tab", lambda: self.action_show_tab("log"))
        yield SystemCommand("Report tab", "Switch to the Report tab", lambda: self.action_show_tab("report"))

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
        self.notify(f"Monitoring {state}", severity="warning" if self._paused else "information")
        self._update_health_bar()

    def action_add_target(self) -> None:
        def on_dismiss(result: str | None) -> None:
            if not result:
                return
            # Case-insensitive: hostnames are case-insensitive by spec (and
            # lower-casing an IP literal is a no-op), so "Google.com" added
            # after "google.com" is a duplicate, not a second target.
            if result.lower() in {t.lower() for t in self._targets}:
                self.notify(f"{result} is already being monitored", severity="warning")
                return
            self._targets.append(result)
            self._latency[result]
            self._mount_sparkline(result)
            self._rebuild_table()
            self._log(f"[green]Added target:[/green] {result}")
            self.notify(f"Added target: {result}", severity="information")
            self._update_health_bar()
            self._run_checks(result)

        self.push_screen(AddTargetScreen(), on_dismiss)

    def action_remove_target(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None or not self._targets:
            self.notify("No target selected", severity="warning")
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
        self._latest_cells.pop(target, None)

        spark = self._sparklines.pop(target, None)
        label = self._spark_labels.pop(target, None)
        if spark is not None:
            spark.remove()
        if label is not None:
            label.remove()

        self._log(f"[red]Removed target:[/red] {target}")
        self.notify(f"Removed target: {target}", severity="warning")
        self._update_health_bar()

    # ── Speed test ────────────────────────────────────────────────────────────

    def action_run_speed_test(self) -> None:
        self.notify("Running speed test…", timeout=3)
        self._run_speed_test()

    @work(thread=True)
    def _run_speed_test(self) -> None:
        size_mb = cfg_mod.load().get("speed", {}).get("size_mb", 10)
        try:
            result = speed_check(size_mb=size_mb)
        except Exception as exc:
            result = {"status": "fail", "error": str(exc)}
        self.call_from_thread(self._show_speed_result, result)

    def _show_speed_result(self, result: dict) -> None:
        if result.get("status") == "ok":
            mbps = result["mbps"]
            latency = result.get("latency_ms")
            msg = f"↓ {mbps:.1f} Mbps" + (f"  ·  {latency:.0f} ms to first byte" if latency else "")
            self.notify(msg, title="Speed test", severity="information", timeout=8)
            self._log(f"[cyan]Speed test:[/cyan] {mbps:.1f} Mbps")
        else:
            error = result.get("error", "speed test failed")
            self.notify(error, title="Speed test failed", severity="error", timeout=8)
            self._log(f"[cyan]Speed test:[/cyan] [red]{error}[/red]")

    # ── WiFi bar ──────────────────────────────────────────────────────────────

    @work(thread=True)
    def _refresh_wifi(self) -> None:
        try:
            result = wifi_check()
        except Exception as exc:
            result = {"status": "fail", "error": str(exc)}
        self.call_from_thread(self._update_wifi_bar, result)

    def _update_wifi_bar(self, result: dict) -> None:
        self.query_one("#wifi-status", Static).update(_render_wifi_text(result))

    # ── Health summary bar ───────────────────────────────────────────────────

    def _update_health_bar(self) -> None:
        total = len(self._targets)
        if total == 0:
            text = "[dim]No targets — press t or open the command palette (ctrl+p) to add one[/dim]"
        else:
            healthy = sum(
                1 for t in self._targets
                if t in self._latest and all(
                    self._latest[t][k]["status"] == "ok" for k in ("dns", "ping", "http", "port", "ssl")
                )
            )
            color = "green" if healthy == total else ("yellow" if healthy else "red")
            state = "[yellow]paused[/yellow]" if self._paused else f"every {self._refresh}s"
            now = datetime.now().strftime("%H:%M:%S")
            text = (
                f"[{color}]●[/{color}] {healthy}/{total} healthy   "
                f"[dim]refresh {state} · last {now}[/dim]"
            )
        self.query_one("#health-status", Static).update(text)

    # ── Worker ────────────────────────────────────────────────────────────────

    @work(thread=True)
    def _run_checks(self, target: str) -> None:
        # Each check is isolated (see _safe_check above): without it, one
        # bad check would blank the entire cycle for this target -- no
        # update, no alert, row stuck on "checking..." forever -- instead
        # of just that one check showing FAIL.
        dns_r  = _safe_check(dns_check, target)
        ping_r = _safe_check(ping_check, target)
        http_r = _safe_check(http_check, target)
        port_r = _safe_check(port_check, target)
        ssl_r  = _safe_check(ssl_check, target, timeout=5)

        # Fire alerts on state transitions
        results_map = {
            "dns":  dns_r,
            "ping": ping_r,
            "http": http_r,
            "port": port_r,
            "ssl":  ssl_r,
        }
        failed_now: list[str] = []
        recovered_now: list[str] = []
        for check_name, result in results_map.items():
            new_state = result["status"]  # "ok" or "fail"
            old_state = self._states[target][check_name]
            if new_state == "fail" and old_state != "fail":
                error = result.get("error", result.get("message", "check failed"))
                alerts_mod.fire(target, check_name, str(error), self._alert_cfg)
                failed_now.append(check_name.upper())
            elif new_state == "ok" and old_state == "fail":
                recovered_now.append(check_name.upper())
            self._states[target][check_name] = new_state

        if failed_now:
            self.call_from_thread(
                self.notify, f"{target}: {', '.join(failed_now)} failing",
                title="Check failed", severity="error", timeout=6,
            )
        if recovered_now:
            self.call_from_thread(
                self.notify, f"{target}: {', '.join(recovered_now)} recovered",
                title="Recovered", severity="information", timeout=4,
            )

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

        # Cache the rendered cells so a filtered-out/back-in target (or a
        # freshly re-rendered table after a filter change) shows the last
        # known values instead of reverting to "checking…".
        self._latest_cells[target] = (dns_cell, ping_cell, http_cell, port_cell, ssl_cell, now)

        if self._target_matches(target):
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
        self._update_health_bar()

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


_HARD_DEFAULT_TARGETS = ["google.com", "1.1.1.1"]
_HARD_DEFAULT_REFRESH = 30


def _valid_config_targets(value: object) -> list[str] | None:
    """A hand-edited config.toml can have `targets = "google.com"` (a typo'd
    string instead of a list) or `targets = []`. list(str) would silently
    iterate character-by-character and list([]) would launch with nothing
    monitored -- neither fails loudly, they just produce nonsense. Return
    None for anything that isn't a usable non-empty list of strings so the
    caller can fall back instead."""
    if not isinstance(value, list) or not value:
        return None
    cleaned = [str(v).strip() for v in value if str(v).strip()]
    return cleaned or None


def _valid_refresh_interval(value: object) -> int | None:
    try:
        interval = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return interval if interval > 0 else None


def run_tui(targets: list[str] | None = None, refresh_interval: int | None = None) -> None:
    cfg = cfg_mod.defaults()

    t = targets or _valid_config_targets(cfg.get("targets"))
    if t is None:
        t = _HARD_DEFAULT_TARGETS
        print(f"[nethealth] config.toml has no usable [defaults].targets -- using {t}")

    r = refresh_interval or _valid_refresh_interval(cfg.get("refresh_interval"))
    if r is None:
        r = _HARD_DEFAULT_REFRESH
        print(f"[nethealth] config.toml has no usable [defaults].refresh_interval -- using {r}s")

    NetHealthTUI(t, r).run()
