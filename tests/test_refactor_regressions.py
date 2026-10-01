"""Regressions found in the 2026-10 refactor pass. Each test failed on the
pre-refactor code (556d59c)."""
from __future__ import annotations

import json
import threading
import tomllib

import pytest
from textual.widgets import DataTable

from nethealth import config as cfg_mod
from nethealth import report as report_mod
from nethealth import tui as tui_mod
from nethealth.tui import NetHealthTUI


def test_config_save_escapes_quotes_and_backslashes(isolated_config):
    cfg_mod.save({
        "defaults": {"targets": ['we"ird', r"c:\path"], "refresh_interval": 15},
        "alerts": {"webhook_url": 'https://x.test/?q="a"'},
    })
    data = tomllib.loads(cfg_mod.CONFIG_PATH.read_text())
    assert data["defaults"]["targets"] == ['we"ird', r"c:\path"]
    assert data["alerts"]["webhook_url"] == 'https://x.test/?q="a"'


def test_concurrent_history_writes_lose_nothing(tmp_path):
    path = tmp_path / "history.json"
    threads = [
        threading.Thread(target=report_mod.record_check,
                         args=(f"t{i}", {"dns": {"status": "ok", "latency": 1.0}}, path))
        for i in range(40)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(json.loads(path.read_text())) == 40


@pytest.mark.asyncio
async def test_result_for_removed_target_is_dropped(monkeypatch):
    app = NetHealthTUI(["a.test", "b.test"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(DataTable).move_cursor(row=0)
        app.action_remove_target()  # removes a.test (row 0)
        ok = {"status": "ok", "latency": 1.0, "avg_ms": 1.0, "code": 200,
              "results": [{"port": 443, "status": "open"}], "days_left": 90}
        # A worker that started before the removal finishes afterwards.
        app._update_ui("a.test", dict.fromkeys(("dns", "ping", "http", "port", "ssl"), ok))
        await pilot.pause()
        assert app.query_one(DataTable).row_count == 1
        assert "a.test" not in app._latest


# ── traceroute raw reply matching ───────────────────────────────────────

import socket as _socket
import struct as _struct

from nethealth.checks import traceroute as tr_mod


def _ip(payload: bytes, ihl_words: int = 5) -> bytes:
    options = b"\x01" * ((ihl_words - 5) * 4)  # NOP options
    header = _struct.pack(
        "!BBHHHBBH4s4s", (4 << 4) | ihl_words, 0, ihl_words * 4 + len(payload),
        0, 0, 64, 1, 0, _socket.inet_aton("10.0.0.1"), _socket.inet_aton("10.0.0.2"),
    )
    return header + options + payload


def _icmp_reply(icmp_type: int, code: int, probe_port: int, inner_ihl_words: int = 5) -> bytes:
    udp = _struct.pack("!HHHH", 40000, probe_port, 8, 0)
    inner = _ip(udp, inner_ihl_words)
    return _struct.pack("!BBHI", icmp_type, code, 0, 0) + inner


def test_classify_handles_ip_options_on_outer_and_inner_headers():
    pkt = _ip(_icmp_reply(11, 0, 33435, inner_ihl_words=6), ihl_words=7)
    assert tr_mod._classify_icmp_reply(pkt, 33435) == "time_exceeded"


def test_classify_ignores_reply_to_a_different_probe():
    pkt = _ip(_icmp_reply(3, 3, 33499))
    assert tr_mod._classify_icmp_reply(pkt, 33435) is None


class _FakeSock:
    def __init__(self, packets):
        self.packets = list(packets)

    def settimeout(self, _):
        pass

    def recvfrom(self, _):
        if not self.packets:
            raise _socket.timeout()
        return self.packets.pop(0), ("192.0.2.9", 0)


def test_stray_icmp_does_not_drop_the_hop():
    stray = _ip(_icmp_reply(11, 0, 33499))
    ours = _ip(_icmp_reply(3, 3, 33435))
    hop = tr_mod._await_hop_reply(_FakeSock([stray, ours]), 33435, timeout=2)
    assert hop["type"] == "destination_reached"
    assert hop["address"] == "192.0.2.9"


def test_system_traceroute_hops_are_ints_and_skip_continuation_lines():
    out = (
        "traceroute to x (1.2.3.4), 30 hops max\n"
        " 1  gw (10.0.0.1)  1.0 ms\n"
        "    alt (10.0.0.9)  1.2 ms\n"
        " 2  * * *\n"
    )
    hops = tr_mod._parse_system_output(out)
    assert [h["hop"] for h in hops] == [1, 2]


# ── ping monitor ─────────────────────────────────────────────────────────

from nethealth.checks.ping_monitor import _log_name


def test_ping_log_names_do_not_collide_and_are_path_safe():
    names = {_log_name(t) for t in ("a.b", "a_b", "fe80::1", "a-b")}
    assert len(names) == 4
    assert all(":" not in n and "/" not in n for n in names)


# ── TUI worker ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slow_target_does_not_stack_workers():
    app = NetHealthTUI(["a.test"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._inflight.add("a.test")  # a cycle is still running
        started = []
        app._check_worker = lambda t: started.append(t)  # type: ignore[method-assign]
        app._run_checks("a.test")
        app._run_checks("a.test")
        assert started == []
