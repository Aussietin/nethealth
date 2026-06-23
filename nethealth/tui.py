"""
nethealth/tui.py — Textual TUI for nethealth
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
)

from nethealth.checks.dns import dns_check
from nethealth.checks.http import http_check
from nethealth.checks.ping import ping_check
from nethealth.checks.port import port_check

MAX_SPARKLINE_POINTS = 60
REFRESH_INTERVAL = 30

_COL_TARGET  = "Target"
_COL_DNS     = "DNS"
_COL_PING    = "Ping"
_COL_HTTP    = "HTTP"
_COL_PORT    = "Port"
_COL_UPDATED = "Updated"


def _cell(text: str, ok: bool | None) -> Text:
    """Rich Text with green/red/dim styling for DataTable cells."""
    if ok is None:
        return Text(text, style="dim")
    return Text(text, style="green" if ok else "red")


class AddTargetScreen(ModalScreen):
    """Floating dialog to add a new monitoring target."""

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
    """Textual TUI — live network health monitor."""

    TITLE = "nethealth"
    SUB_TITLE = "Network Health Monitor"

    BINDINGS: ClassVar[list] = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "add_target", "Add target"),
    ]

    DEFAULT_CSS = """
    #main { height: 1fr; }
    #left {
        width: 58%;
        border-right: solid $primary-darken-2;
    }
    #right { width: 42%; }
    .panel-title {
        background: $primary-darken-3;
        padding: 0 1;
        color: $text;
        text-style: bold;
    }
    DataTable { height: 1fr; }
    #spark-scroll {
        height: 1fr;
        padding: 0 1;
    }
    Sparkline {
        height: 5;
        margin-bottom: 0;
    }
    .spark-label { margin-top: 1; }
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
        self._spark_labels: dict[str, Label] = {}
        # packet loss tracking: {target: [sent, ok]}
        self._ping_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])

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
            table.add_row(target, _cell("—", None), _cell("—", None), _cell("—", None), _cell("—", None), "—", key=target)
            self._mount_sparkline(target)

        self._log(f"[cyan]nethealth TUI started[/cyan] — watching {len(self._targets)} target(s)")
        self._log("[dim]Auto-refresh every 30 s · [b]r[/b] refresh · [b]t[/b] add target · [b]q[/b] quit[/dim]")
        self.set_interval(REFRESH_INTERVAL, self.action_refresh)
        self.action_refresh()

    def _mount_sparkline(self, target: str) -> None:
        scroll = self.query_one("#spark-scroll")
        label = Label(f"[dim]{target}[/dim]", classes="spark-label")
        spark = Sparkline([], summary_function=max)
        self._sparklines[target] = spark
        self._spark_labels[target] = label
        scroll.mount(label)
        scroll.mount(spark)

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
        self.call_from_thread(self._update_ui, target, dns_r, ping_r, http_r, port_r)

    def _update_ui(
        self,
        target: str,
        dns_r: dict,
        ping_r: dict,
        http_r: dict,
        port_r: dict,
    ) -> None:
        def _ok(r: dict) -> bool:
            return r["status"] == "ok"

        # Ping stats + sparkline
        stats = self._ping_stats[target]
        stats[0] += 1  # sent
        ping_ok = _ok(ping_r)
        if ping_ok:
            stats[1] += 1  # received
        loss_pct = (1 - stats[1] / stats[0]) * 100 if stats[0] else 0.0

        avg = ping_r.get("avg_ms")
        if ping_ok and avg is not None:
            self._latency[target].append(avg)
            spark = self._sparklines.get(target)
            if spark is not None:
                spark.data = list(self._latency[target])

        # Update sparkline label with live stats
        label = self._spark_labels.get(target)
        if label is not None:
            loss_color = "green" if loss_pct == 0 else ("yellow" if loss_pct < 10 else "red")
            ms_part = f"  {avg:.0f} ms" if (ping_ok and avg is not None) else ""
            label.update(
                f"[dim]{target}[/dim]{ms_part}  [{loss_color}]loss {loss_pct:.0f}%[/{loss_color}]"
            )

        # Build coloured cells
        dns_cell  = _cell(f"{dns_r.get('latency', 0):.0f} ms", _ok(dns_r)) if _ok(dns_r) else _cell("FAIL", False)
        ping_cell = _cell(f"{avg:.0f} ms  loss {loss_pct:.0f}%", ping_ok) if (ping_ok and avg is not None) else _cell("FAIL", False)
        http_cell = _cell(f"{http_r.get('code', '?')}", _ok(http_r)) if _ok(http_r) else _cell("FAIL", False)
        open_ports = [str(x["port"]) for x in port_r.get("results", []) if x["status"] == "open"]
        port_cell = _cell(",".join(open_ports), True) if open_ports else _cell("closed", False)
        now = datetime.now().strftime("%H:%M:%S")

        table = self.query_one(DataTable)
        table.update_cell(target, _COL_DNS,     dns_cell,  update_width=True)
        table.update_cell(target, _COL_PING,    ping_cell, update_width=True)
        table.update_cell(target, _COL_HTTP,    http_cell, update_width=True)
        table.update_cell(target, _COL_PORT,    port_cell, update_width=True)
        table.update_cell(target, _COL_UPDATED, now,       update_width=True)

        icons = "".join(
            "✓" if _ok(r) else "✗"
            for r in [dns_r, ping_r, http_r, port_r]
        )
        all_ok = all(_ok(r) for r in [dns_r, ping_r, http_r, port_r])
        color = "green" if all_ok else "red"
        self._log(
            f"[{color}]{icons}[/{color}] [bold]{target}[/bold]"
            + (f"  ping {avg:.0f} ms" if (ping_ok and avg is not None) else "")
            + (f"  loss {loss_pct:.0f}%" if stats[0] > 1 else "")
            + f"  [dim]{now}[/dim]"
        )

    def _log(self, msg: str) -> None:
        self.query_one(RichLog).write(msg)


def run_tui(targets: list[str]) -> None:
    """Entry point called from the CLI."""
    NetHealthTUI(targets).run()