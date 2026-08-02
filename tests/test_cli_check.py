"""CLI tests for `nethealth check` -- the primary one-shot command, and
its output formatters. Never had direct coverage before; only the
underlying check_* functions were tested. cli.py imports dns_check /
ping_check / http_check / port_check / traceroute_check directly into its
own namespace (not deferred, unlike gateway/ip), so they're patched as
nethealth.cli.<name> here, not on the checks submodules."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import nethealth.cli as cli_mod
from nethealth.cli import cli

_OK_RESULTS = {
    "dns": {"status": "ok", "latency": 12.3},
    "ping": {"status": "ok", "avg_ms": 8.1},
    "http": {"status": "ok", "code": 200, "latency": 55.0},
    "port": {"status": "ok", "results": [{"port": 443, "status": "open"}]},
}

_FAIL_RESULTS = {
    "dns": {"status": "fail", "error": "NXDOMAIN"},
    "ping": {"status": "fail", "error": "100% packet loss"},
    "http": {"status": "fail", "error": "connection refused"},
    "port": {"status": "fail", "results": [{"port": 443, "status": "closed"}]},
}


def _patch_checks(monkeypatch, results: dict, traceroute: dict | None = None):
    monkeypatch.setattr(cli_mod, "dns_check", lambda t: results["dns"])
    monkeypatch.setattr(cli_mod, "ping_check", lambda t: results["ping"])
    monkeypatch.setattr(cli_mod, "http_check", lambda t: results["http"])
    monkeypatch.setattr(cli_mod, "port_check", lambda t: results["port"])
    if traceroute is not None:
        monkeypatch.setattr(cli_mod, "traceroute_check", lambda t, max_hops=15: traceroute)


# ── formatters (pure functions) ──────────────────────────────────────────

def test_fmt_dns_ok():
    assert "12.3" in cli_mod._fmt_dns({"status": "ok", "latency": 12.3})


def test_fmt_dns_fail():
    assert cli_mod._fmt_dns({"status": "fail", "error": "timeout"}) == "timeout"


def test_fmt_ping_ok():
    assert "8.1" in cli_mod._fmt_ping({"status": "ok", "avg_ms": 8.1})


def test_fmt_http_ok():
    label = cli_mod._fmt_http({"status": "ok", "code": 200, "latency": 55.0})
    assert "200" in label
    assert "55" in label


def test_fmt_port_open():
    label = cli_mod._fmt_port({"results": [{"port": 443, "status": "open"}, {"port": 22, "status": "closed"}]})
    assert "443" in label
    assert "22" not in label


def test_fmt_port_all_closed():
    label = cli_mod._fmt_port({"results": [{"port": 22, "status": "closed"}]})
    assert "closed" in label


def test_fmt_status_ok_and_fail():
    assert "OK" in cli_mod._fmt_status("ok")
    assert "FAIL" in cli_mod._fmt_status("fail")


# ── `check` command ───────────────────────────────────────────────────────

def test_check_command_all_passing(monkeypatch):
    _patch_checks(monkeypatch, _OK_RESULTS, traceroute={"status": "ok", "hops": [{"hop": 1, "address": "1.1.1.1", "latency": 1.0}]})
    result = CliRunner().invoke(cli, ["check", "example.com"])
    assert result.exit_code == 0
    assert "5/5" in result.output


def test_check_command_some_failing(monkeypatch):
    _patch_checks(monkeypatch, _FAIL_RESULTS, traceroute={"status": "fail", "message": "no route"})
    result = CliRunner().invoke(cli, ["check", "example.com"])
    assert result.exit_code == 0
    assert "0/5" in result.output


def test_check_command_skip_traceroute(monkeypatch):
    _patch_checks(monkeypatch, _OK_RESULTS)
    result = CliRunner().invoke(cli, ["check", "example.com", "--skip-traceroute"])
    assert result.exit_code == 0
    assert "4/4" in result.output


def test_check_command_json_output(monkeypatch):
    _patch_checks(monkeypatch, _OK_RESULTS, traceroute={"status": "ok", "hops": []})
    result = CliRunner().invoke(cli, ["check", "example.com", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["target"] == "example.com"
    assert data["results"]["dns"]["status"] == "ok"


def test_check_command_save_json(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _patch_checks(monkeypatch, _OK_RESULTS, traceroute={"status": "ok", "hops": []})
    result = CliRunner().invoke(cli, ["check", "example.com", "--save", "json", "--skip-traceroute"])
    assert result.exit_code == 0
    history_path = tmp_path / ".nethealth" / "history.json"
    assert history_path.exists()
    data = json.loads(history_path.read_text())
    assert data[0]["target"] == "example.com"


def test_check_command_save_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _patch_checks(monkeypatch, _OK_RESULTS, traceroute={"status": "ok", "hops": []})
    result = CliRunner().invoke(cli, ["check", "example.com", "--save", "csv", "--skip-traceroute"])
    assert result.exit_code == 0
    csv_path = tmp_path / ".nethealth" / "history.csv"
    assert csv_path.exists()
    content = csv_path.read_text()
    assert "example.com" in content
    assert "timestamp,target,check,status,detail" in content
