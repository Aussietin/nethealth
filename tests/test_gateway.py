"""Unit tests for nethealth/checks/gateway.py -- default-route parsing and
the ping-the-gateway flow, with subprocess/ping_check mocked out."""
from __future__ import annotations

import subprocess

from nethealth.checks import gateway as gw_mod


def test_default_gateway_linux_parses_ip_route_output(monkeypatch):
    fake_proc = subprocess.CompletedProcess(
        args=["ip"], returncode=0,
        stdout="default via 192.168.1.1 dev eth0 proto dhcp metric 100\n",
        stderr="",
    )
    monkeypatch.setattr(gw_mod.subprocess, "run", lambda *a, **kw: fake_proc)
    assert gw_mod._default_gateway_linux() == "192.168.1.1"


def test_default_gateway_linux_no_default_route(monkeypatch):
    fake_proc = subprocess.CompletedProcess(args=["ip"], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(gw_mod.subprocess, "run", lambda *a, **kw: fake_proc)
    assert gw_mod._default_gateway_linux() is None


def test_default_gateway_linux_command_missing(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError()

    monkeypatch.setattr(gw_mod.subprocess, "run", _raise)
    assert gw_mod._default_gateway_linux() is None


def test_default_gateway_linux_nonzero_exit(monkeypatch):
    fake_proc = subprocess.CompletedProcess(args=["ip"], returncode=1, stdout="", stderr="error")
    monkeypatch.setattr(gw_mod.subprocess, "run", lambda *a, **kw: fake_proc)
    assert gw_mod._default_gateway_linux() is None


def test_gateway_check_ok(monkeypatch):
    monkeypatch.setattr(gw_mod, "_default_gateway_linux", lambda: "192.168.1.1")
    monkeypatch.setattr(gw_mod, "ping_check", lambda host: {"status": "ok", "avg_ms": 2.5})

    result = gw_mod.gateway_check()
    assert result["status"] == "ok"
    assert result["gateway"] == "192.168.1.1"
    assert result["avg_ms"] == 2.5


def test_gateway_check_no_route_found(monkeypatch):
    monkeypatch.setattr(gw_mod, "_default_gateway_linux", lambda: None)
    result = gw_mod.gateway_check()
    assert result["status"] == "fail"
    assert "gateway" not in result


def test_gateway_check_unreachable(monkeypatch):
    monkeypatch.setattr(gw_mod, "_default_gateway_linux", lambda: "192.168.1.1")
    monkeypatch.setattr(
        gw_mod, "ping_check",
        lambda host: {"status": "fail", "error": "100% packet loss"},
    )
    result = gw_mod.gateway_check()
    assert result["status"] == "fail"
    assert result["gateway"] == "192.168.1.1"
    assert "error" in result
