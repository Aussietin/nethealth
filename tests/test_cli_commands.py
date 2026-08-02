"""CLI smoke tests for the new `gateway` and `ip` commands, via Click's
CliRunner with the underlying check functions mocked out."""
from __future__ import annotations

import json

from click.testing import CliRunner

from nethealth.cli import cli


def test_gateway_command_ok(monkeypatch):
    import nethealth.checks.gateway as gw_mod
    monkeypatch.setattr(
        gw_mod, "gateway_check",
        lambda: {"status": "ok", "gateway": "192.168.1.1", "avg_ms": 2.0},
    )
    result = CliRunner().invoke(cli, ["gateway"])
    assert result.exit_code == 0
    assert "192.168.1.1" in result.output


def test_gateway_command_fail(monkeypatch):
    import nethealth.checks.gateway as gw_mod
    monkeypatch.setattr(
        gw_mod, "gateway_check",
        lambda: {"status": "fail", "error": "no default route"},
    )
    result = CliRunner().invoke(cli, ["gateway"])
    assert result.exit_code == 0
    assert "no default route" in result.output


def test_ip_command_ok(monkeypatch):
    import nethealth.checks.public_ip as ip_mod
    monkeypatch.setattr(
        ip_mod, "public_ip_check",
        lambda: {"status": "ok", "ip": "203.0.113.5"},
    )
    result = CliRunner().invoke(cli, ["ip"])
    assert result.exit_code == 0
    assert "203.0.113.5" in result.output


def test_ip_command_json_output(monkeypatch):
    import nethealth.checks.public_ip as ip_mod
    monkeypatch.setattr(
        ip_mod, "public_ip_check",
        lambda: {"status": "ok", "ip": "203.0.113.5"},
    )
    result = CliRunner().invoke(cli, ["ip", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ip"] == "203.0.113.5"


def test_ip_command_fail(monkeypatch):
    import nethealth.checks.public_ip as ip_mod
    monkeypatch.setattr(
        ip_mod, "public_ip_check",
        lambda: {"status": "fail", "error": "timed out"},
    )
    result = CliRunner().invoke(cli, ["ip"])
    assert result.exit_code == 0
    assert "timed out" in result.output


def test_help_lists_new_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "gateway" in result.output
    assert "ip" in result.output
