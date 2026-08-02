"""Unit tests for nethealth/checks/traceroute.py's system-traceroute path
(the raw-socket path needs root and isn't exercised here)."""
from __future__ import annotations

import subprocess

from nethealth.checks import traceroute as tr_mod


def test_system_traceroute_missing_binary(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError()

    monkeypatch.setattr(tr_mod.subprocess, "run", _raise)
    result = tr_mod._system_traceroute("example.com")
    assert result["status"] == "fail"
    assert "traceroute" in result["message"].lower()
    assert "not found" in result["message"].lower()


def test_system_traceroute_timeout(monkeypatch):
    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="traceroute", timeout=5)

    monkeypatch.setattr(tr_mod.subprocess, "run", _raise)
    result = tr_mod._system_traceroute("example.com")
    assert result["status"] == "fail"
    assert "timed out" in result["message"].lower()


def test_system_traceroute_parses_hops(monkeypatch):
    fake_stdout = (
        "traceroute to example.com (93.184.216.34), 30 hops max\n"
        " 1  192.168.1.1 (192.168.1.1)  1.234 ms\n"
        " 2  * * *\n"
        " 3  93.184.216.34 (93.184.216.34)  10.5 ms\n"
    )
    fake_proc = subprocess.CompletedProcess(
        args=["traceroute"], returncode=0, stdout=fake_stdout, stderr="",
    )
    monkeypatch.setattr(tr_mod.subprocess, "run", lambda *a, **kw: fake_proc)
    result = tr_mod._system_traceroute("example.com")
    assert result["status"] == "ok"
    assert len(result["hops"]) == 3
    assert result["hops"][0]["address"] == "192.168.1.1"


def test_system_traceroute_nonzero_exit(monkeypatch):
    fake_proc = subprocess.CompletedProcess(
        args=["traceroute"], returncode=1, stdout="", stderr="Name or service not known",
    )
    monkeypatch.setattr(tr_mod.subprocess, "run", lambda *a, **kw: fake_proc)
    result = tr_mod._system_traceroute("doesnotexist.invalid")
    assert result["status"] == "fail"


def test_traceroute_check_uses_system_path_when_not_root(monkeypatch):
    monkeypatch.setattr(tr_mod.sys, "platform", "win32")  # force the non-Linux-root branch
    called = {}

    def _fake_system(target, max_hops=30):
        called["target"] = target
        return {"name": "Traceroute", "status": "ok", "method": "system", "hops": [], "target": target}

    monkeypatch.setattr(tr_mod, "_system_traceroute", _fake_system)
    result = tr_mod.traceroute_check("example.com")
    assert result["status"] == "ok"
    assert called["target"] == "example.com"
