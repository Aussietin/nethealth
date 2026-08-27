"""Tests for nethealth.diagnose (plain-language verdict logic) and the
`nethealth status` CLI command / default invocation."""
from __future__ import annotations

from click.testing import CliRunner

from nethealth.cli import cli
from nethealth.diagnose import diagnose, OK, WARN, DOWN


OK_GW = {"status": "ok", "gateway": "192.168.0.1", "avg_ms": 2.0}
OK_DNS = {"status": "ok", "latency": 20.0}
OK_PING = {"status": "ok", "avg_ms": 15.0}
OK_HTTP = {"status": "ok", "code": 200, "latency": 120.0}


def test_all_healthy():
    r = diagnose(gateway=OK_GW, dns=OK_DNS, ping=OK_PING, http=OK_HTTP, target="google.com")
    assert r.severity == OK
    assert "working normally" in r.headline
    assert any("Router responds" in d for d in r.details)


def test_gateway_down_is_the_headline():
    r = diagnose(
        gateway={"status": "fail", "error": "no default route"},
        dns=OK_DNS, ping=OK_PING, http=OK_HTTP,
    )
    assert r.severity == DOWN
    assert "router or modem" in r.headline
    assert any("Restart your router" in s for s in r.suggestions)


def test_no_internet_but_local_ok():
    r = diagnose(
        gateway=OK_GW,
        dns={"status": "fail", "error": "timeout"},
        ping={"status": "fail", "error": "100% loss"},
        http={"status": "fail", "error": "connect error"},
    )
    assert r.severity == DOWN
    assert "No internet connection" in r.headline


def test_dns_failure_detected_specifically():
    r = diagnose(gateway=OK_GW, dns={"status": "fail", "error": "NXDOMAIN"},
                 ping=OK_PING, http=OK_HTTP, target="google.com")
    assert r.severity == DOWN
    assert "DNS" in r.headline
    assert any("1.1.1.1" in s for s in r.suggestions)


def test_single_site_down_is_only_a_warning():
    r = diagnose(gateway=OK_GW, dns=OK_DNS, ping=OK_PING,
                 http={"status": "fail", "error": "503"}, target="example.com")
    assert r.severity == WARN
    assert "example.com" in r.headline


def test_slow_connection_is_a_warning():
    r = diagnose(gateway=OK_GW, dns=OK_DNS,
                 ping={"status": "ok", "avg_ms": 500.0}, http=OK_HTTP, target="google.com")
    assert r.severity == WARN
    assert "very slow" in r.headline


def test_mildly_slow_wording():
    r = diagnose(gateway=OK_GW, dns=OK_DNS,
                 ping={"status": "ok", "avg_ms": 200.0}, http=OK_HTTP, target="google.com")
    assert r.severity == WARN
    assert "little slower" in r.headline


def test_gateway_only_pass():
    r = diagnose(gateway=OK_GW)
    assert r.severity == OK
    assert "local network" in r.headline


def _patch_checks(monkeypatch, *, gw=OK_GW, dns=OK_DNS, ping=OK_PING, http=OK_HTTP):
    import nethealth.cli as cli_mod
    import nethealth.checks.gateway as gw_mod
    monkeypatch.setattr(gw_mod, "gateway_check", lambda: gw)
    monkeypatch.setattr(cli_mod, "dns_check", lambda t: dns)
    monkeypatch.setattr(cli_mod, "ping_check", lambda t: ping)
    monkeypatch.setattr(cli_mod, "http_check", lambda t: http)


def test_status_command_healthy(monkeypatch):
    _patch_checks(monkeypatch)
    result = CliRunner().invoke(cli, ["status", "google.com"])
    assert result.exit_code == 0
    assert "working normally" in result.output


def test_bare_invocation_runs_status(monkeypatch, isolated_config):
    _patch_checks(monkeypatch, http={"status": "fail", "error": "boom"})
    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0
    assert "isn't responding" in result.output


def test_status_json_output(monkeypatch):
    _patch_checks(monkeypatch)
    result = CliRunner().invoke(cli, ["status", "google.com", "--json"])
    assert result.exit_code == 0
    assert '"severity": "ok"' in result.output


def test_check_prints_plain_language_verdict(monkeypatch):
    import nethealth.cli as cli_mod
    monkeypatch.setattr(cli_mod, "dns_check", lambda t: OK_DNS)
    monkeypatch.setattr(cli_mod, "ping_check", lambda t: OK_PING)
    monkeypatch.setattr(cli_mod, "http_check", lambda t: {"status": "fail", "error": "boom"})
    monkeypatch.setattr(cli_mod, "port_check", lambda t: {"status": "ok", "results": []})
    monkeypatch.setattr(cli_mod, "traceroute_check", lambda t, **k: {"status": "ok", "hops": []})
    result = CliRunner().invoke(cli, ["check", "example.com"])
    assert result.exit_code == 0
    assert "example.com isn't responding" in result.output
