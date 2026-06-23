"""
nethealth/tui.py — Textual TUI for nethealth
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import ClassVar

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
)

from nethealth.checks.dns import dns_check
from nethealth.checks.http import http_check
from nethealth.checks.ping import ping_check
from nethealth.checks.port import port_check

MAX_SPARKLINE_POINTS = 60
REFRESH_INTERVAL = 30  # seconds between auto-refreshes

_COL_TARGET = "Target"
_COL_DNS = "DNS"
_COL_PING = "Ping"
_COL_HTTP = "HTTP"
_COL_PORT = "Port"
_COL_UPDATED = "Updated"


class AddTargetScreen(ModalScreen):
    """Floating dialog to add a new monitoring target."""

    DEFAULT_CSS = """
    AddTargetScreen {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 52;
        height: 7;
    }
    #dialog Label {
        margin-bottom: 1;
    }
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
    """Textual TUI — live network health monitor."""

    TITLE = "nethealth"
    SUB_TITLE = "Network Health Monitor"

    BINDINGS: ClassVar[list] = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "add_target", "Add target"),
    ]

    DEFAULT_CSS = """
    #main {
        height: 1fr;
    }
    #left {
        width: 58%;
        border-right: solid $primary-darken-2;
    }
    #right {
        width: 42%;
    }
    .panel-title {
        background: $primary-darken-3;
        padding: 0 1;
        color: $text;
        text-style: bold;
    }
    DataTable {
        height: 1fr;
    }
    #spark-scroll {
        height: 1fr;
        padding: 0 1;
    }
    Sparkline {
        height: 5;
        margin-bottom: 1;
    }
    .spark-label {
        color: $text-muted;
    }
    #log {
        height: 12;
        border-top: solid $primary-darken-2;
    }
    """

    def __init__(self, targets: list[str]) -> None:
        super().__init__()
        self._targets: list[str] = list(targets)
        self._latency: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_SPARKLINE_POINTS))
        self._sparklines: dict[str, Sparkline] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static("  Status", classes="panel-title")
                yield DataTable(id="status-table", cursor_type="row")
            with Vertical(id="right"):
                yield Static("  Ping Latency (ms)", classes="panel-title")
                with VerticalScroll(id="spark-scroll"):
                    pass
        yield RichLog(id="log", highlight=True, markup=True, wrap=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for col in [_COL_TARGET, _COL_DNS, _COL_PING, _COL_HTTP, _COL_PORT, _COL_UPDATED]:
            table.add_column(col, key=col)

        for target in self._targets:
            table.add_row(target, "—", "—", "—", "—", "—", key=target)
            self._mount_sparkline(target)

        self._log(f"[cyan]nethealth TUI started[/cyan] — watching {len(self._targets)} target(s)")
        self._log("[dim]Auto-refresh every 30 s. Press [b]r[/b] to refresh now, [b]t[/b] to add a target.[/dim]")
        self.set_interval(REFRESH_INTERVAL, self.action_refresh)
        self.action_refresh()

    def _mount_sparkline(self, target: str) -> None:
        scroll = self.query_one("#spark-scroll")
        label = Label(f"[dim]{target}[/dim]", classes="spark-label")
        spark = Sparkline([], summary_function=max)
        self._sparklines[target] = spark
        scroll.mount(label)
        scroll.mount(spark)

    def action_refresh(self) -> None:
        for target in self._targets:
            self._run_checks(target)

    def action_add_target(self) -> None:
        def on_dismiss(result: str | None) -> None:
            if not result or result in self._targets:
                return
            self._targets.append(result)
            self.query_one(DataTable).add_row(result, "—", "—", "—", "—", "—", key=result)
            self._latency[result]
            self._mount_sparkline(result)
            self._log(f"[green]Added target:[/green] {result}")
            self._run_checks(result)

        self.push_screen(AddTargetScreen(), on_dismiss)

    @work(thread=True)
    def _run_checks(self, target: str) -> None:
        self.call_from_thread(self._log, f"[dim]Checking {target}...[/dim]")
        try:
            dns_r  = dns_check(target)
            ping_r = ping_check(target)
            http_r = http_check(target)
            port_r = port_check(target)
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Error checking {target}: {exc}[/red]")
            return
        self.call_from_thread(self._update_ui, target, dns_r, ping_r, http_r, port_r)

    def _update_ui(
        self,
        target: str,
        dns_r: dict,
        ping_r: dict,
        http_r: dict,
        port_r: dict,
    ) -> None:
        if ping_r["status"] == "ok" and ping_r.get("avg_ms") is not None:
            self._latency[target].append(ping_r["avg_ms"])
            spark = self._sparklines.get(target)
            if spark is not None:
                spark.data = list(self._latency[target])

        def _ok(r: dict) -> bool:
            return r["status"] == "ok"

        def _icon(r: dict) -> str:
            return "OK" if _ok(r) else "FAIL"

        dns_cell  = (f"OK {dns_r.get('latency', 0):.0f}ms") if _ok(dns_r) else "FAIL"
        avg = ping_r.get("avg_ms")
        ping_cell = (f"OK {avg:.0f}ms" if avg is not None else "OK") if _ok(ping_r) else "FAIL"
        http_cell = (f"OK {http_r.get('code', '?')}") if _ok(http_r) else "FAIL"
        open_ports = [str(x["port"]) for x in port_r.get("results", []) if x["status"] == "open"]
        port_cell = (f"OK {','.join(open_ports)}") if open_ports else "CLOSED"
        now = datetime.now().strftime("%H:%M:%S")

        table = self.query_one(DataTable)
        table.update_cell(target, _COL_DNS,     dns_cell,  update_width=True)
        table.update_cell(target, _COL_PING,    ping_cell, update_width=True)
        table.update_cell(target, _COL_HTTP,    http_cell, update_width=True)
        table.update_cell(target, _COL_PORT,    port_cell, update_width=True)
        table.update_cell(target, _COL_UPDATED, now,       update_width=True)

        self._log(
            f"[bold]{target}[/bold]  "
            f"DNS:{_icon(dns_r)} Ping:{_icon(ping_r)} HTTP:{_icon(http_r)} Port:{_icon(port_r)}"
            f"  [dim]{now}[/dim]"
        )

    def _log(self, msg: str) -> None:
        self.query_one(RichLog).write(msg)


def run_tui(targets: list[str]) -> None:
    """Entry point called from the CLI."""
    NetHealthTUI(targets).run()