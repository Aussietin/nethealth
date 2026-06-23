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
from nethealth.report import generate_report

MAX_SPARKLINE_POINTS = 60

_COL_TARGET  = "Target"
_COL_DNS     = "DNS"
_COL_PING    = "Ping"
_COL_HTTP    = "HTTP"
_COL_PORT    = "Port"
_COL_UPDATED = "Updated"

_CHECKS = [_COL_DNS, _COL_PING, _COL_HTTP, _COL_PORT]


def _cell(text: str, ok: bool | None) -> Text:
    if ok is None:
        return Text(text, style="dim")
    return Text(text, style="green" if ok else "red bold")


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


class NetHealthTUI(App):
    TITLE = "nethealth"
    SUB_TITLE = "Network Health Monitor"

    BINDINGS: ClassVar[list] = [
        Binding("q",   "quit",         "Quit"),
        Binding("r",   "refresh",      "Refresh"),
        Binding("t",   "add_target",   "Add target"),
        Binding("1",   "show_tab('monitor')", "Monitor",  show=False),
        Binding("2",   "show_tab('log')",     "Log",      show=False),
        Binding("3",   "show_tab('report')",  "Report",   show=False),
    ]

    DEFAULT_CSS = """
    TabbedContent, TabPane { height: 1fr; }
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
        self._latency:        dict[str, deque]        = defaultdict(lambda: deque(maxlen=MAX_SPARKLINE_POINTS))
        self._sparklines:     dict[str, Sparkline]    = {}
        self._spark_labels:   dict[str, Label]        = {}
        self._ping_stats:     dict[str, list[int]]    = defaultdict(lambda: [0, 0])
        # state tracking for alerts: {target: {check: "ok"|"fail"|"unknown"}}
        self._states:         dict[str, dict[str, str]] = defaultdict(lambda: defaultdict(lambda: "unknown"))
        self._alert_cfg:      dict                    = cfg_mod.alert_cfg()
        self._report_loaded:  bool                    = False

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
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
        for col in [_COL_TARGET, _COL_DNS, _COL_PING, _COL_HTTP, _COL_PORT, _COL_UPDATED]:
            table.add_column(col, key=col)

        for target in self._targets:
            table.add_row(
                target,
                _cell("—", None), _cell("—", None), _cell("—", None), _cell("—", None), "—",
                key=target,
            )
            self._mount_sparkline(target)

        self._log(f"[cyan]nethealth TUI[/cyan] — watching {len(self._targets)} target(s)  "
                  f"[dim]refresh every {self._refresh}s · keys: r refresh · t add target · 1/2/3 tabs · q quit[/dim]")

        self.set_interval(self._refresh, self.action_refresh)
        self.action_refresh()

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

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        for target in self._targets:
            self._run_checks(target)

    def action_add_target(self) -> None:
        def on_dismiss(result: str | None) -> None:
            if not result or result in self._targets:
                return
            self._targets.append(result)
            self.query_one(DataTable).add_row(
                result,
                _cell("—", None), _cell("—", None), _cell("—", None), _cell("—", None), "—",
                key=result,
            )
            self._latency[result]
            self._mount_sparkline(result)
            self._log(f"[green]Added target:[/green] {result}")
            self._run_checks(result)

        self.push_screen(AddTargetScreen(), on_dismiss)

    # ── Worker ────────────────────────────────────────────────────────────────

    @work(thread=True)
    def _run_checks(self, target: str) -> None:
        try:
            dns_r  = dns_check(target)
            ping_r = ping_check(target)
            http_r = http_check(target)
            port_r = port_check(target)
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Error checking {target}: {exc}[/red]")
            return

        # Fire alerts on state transitions
        results_map = {
            "dns":  dns_r,
            "ping": ping_r,
            "http": http_r,
            "port": port_r,
        }
        for check_name, result in results_map.items():
            new_state = result["status"]  # "ok" or "fail"
            old_state = self._states[target][check_name]
            if new_state == "fail" and old_state != "fail":
                error = result.get("error", result.get("message", "check failed"))
                alerts_mod.fire(target, check_name, str(error), self._alert_cfg)
            self._states[target][check_name] = new_state

        self.call_from_thread(self._update_ui, target, dns_r, ping_r, http_r, port_r)

    # ── UI update ─────────────────────────────────────────────────────────────

    def _update_ui(self, target, dns_r, ping_r, http_r, port_r) -> None:
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
        now       = datetime.now().strftime("%H:%M:%S")

        table = self.query_one(DataTable)
        table.update_cell(target, _COL_DNS,     dns_cell,  update_width=True)
        table.update_cell(target, _COL_PING,    ping_cell, update_width=True)
        table.update_cell(target, _COL_HTTP,    http_cell, update_width=True)
        table.update_cell(target, _COL_PORT,    port_cell, update_width=True)
        table.update_cell(target, _COL_UPDATED, now,       update_width=True)

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