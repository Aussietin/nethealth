"""Shared pytest fixtures for the nethealth test suite.

Nothing here touches Austin's real ~/.nethealth, the real network, or real
desktop/webhook alerts:

- history and config always point at a throwaway dir under tmp_path (config
  used to be opt-in, but the TUI reads it on construction, which created a
  real ~/.nethealth/config.toml on any machine that didn't have one);
- TUI tests get instant fake checks -- before this, every pilot test ran real
  DNS/ping/HTTP/SSL against google.com, and teardown waited 5-17 s per test
  for those threads;
- alerts are stubbed everywhere except test_alerts.py, which tests them.
"""
from __future__ import annotations

import pytest

from nethealth import alerts as alerts_mod
from nethealth import checks
from nethealth import config as cfg_mod
from nethealth import report as report_mod

FAKE_RESULTS = {
    "dns": {"name": "DNS", "status": "ok", "latency": 5.0},
    "ping": {"name": "Ping", "status": "ok", "avg_ms": 5.0},
    "http": {"name": "HTTP", "status": "ok", "code": 200, "latency": 20.0, "scheme": "https"},
    "port": {"name": "Port", "status": "ok", "results": [{"port": 443, "status": "open"}]},
    "ssl": {"name": "SSL", "status": "ok", "days_left": 90, "expires": "2027-01-01",
            "subject_cn": "fake", "issuer_o": "fake", "tls_version": "TLSv1.3"},
    "traceroute": {"name": "Traceroute", "status": "ok", "method": "system", "hops": []},
}


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, "HISTORY_PATH", tmp_path / "history.json")
    config_dir = tmp_path / ".nethealth"
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", config_dir / "config.toml")


@pytest.fixture(autouse=True)
def _no_real_alerts(request, monkeypatch):
    if request.module.__name__.endswith("test_alerts"):
        return
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: None)
    monkeypatch.setattr(alerts_mod, "_post", lambda *a: None)


@pytest.fixture(autouse=True)
def _fake_network_for_tui(request, monkeypatch):
    name = request.module.__name__
    if not (name.endswith(("test_refactor_regressions",)) or ".test_tui" in name or name.startswith("test_tui")):
        return
    import nethealth.tui as tui_mod

    for check_name, result in FAKE_RESULTS.items():
        monkeypatch.setitem(checks.TARGET_CHECKS, check_name, lambda t, r=result: dict(r))
    monkeypatch.setattr(tui_mod, "gateway_check",
                        lambda: {"name": "Gateway", "status": "ok", "gateway": "10.0.0.1", "avg_ms": 1.0})
    monkeypatch.setattr(tui_mod, "wifi_check", lambda: {"name": "WiFi", "status": "fail", "error": "test"})


@pytest.fixture
def isolated_config(tmp_path):
    """The throwaway config dir (isolation itself is autouse above)."""
    return tmp_path / ".nethealth"
