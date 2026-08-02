"""Headless pilot tests for batch-2 robustness fixes: per-check isolation in
_run_checks, case-insensitive duplicate-target detection, and config
target/refresh-interval validation in run_tui()."""
from __future__ import annotations

import pytest
from textual.widgets import Input

import nethealth.tui as tui_mod
from nethealth import config as cfg_mod
from nethealth.tui import NetHealthTUI


@pytest.mark.asyncio
async def test_run_checks_isolates_one_failing_check(monkeypatch):
    monkeypatch.setattr(tui_mod, "dns_check", lambda t: {"status": "ok", "latency": 5})
    monkeypatch.setattr(tui_mod, "ping_check", lambda t: {"status": "ok", "avg_ms": 5.0})
    monkeypatch.setattr(tui_mod, "http_check", lambda t: {"status": "ok", "code": 200})
    monkeypatch.setattr(
        tui_mod, "port_check",
        lambda t: {"status": "ok", "results": [{"port": 443, "status": "open"}]},
    )

    def _boom(t, timeout=5):
        raise RuntimeError("boom")

    monkeypatch.setattr(tui_mod, "ssl_check", _boom)

    app = NetHealthTUI(["example.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._run_checks("example.com")
        await pilot.pause(0.3)

        data = app._latest.get("example.com")
        assert data is not None, "an unexpected exception in one check must not blank the whole cycle"
        assert data["dns"]["status"] == "ok"
        assert data["ping"]["status"] == "ok"
        assert data["http"]["status"] == "ok"
        assert data["port"]["status"] == "ok"
        assert data["ssl"]["status"] == "fail"
        assert "internal error" in data["ssl"]["error"]


@pytest.mark.asyncio
async def test_add_target_duplicate_is_case_insensitive():
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        inp = app.screen.query_one(Input)
        inp.value = "Google.com"
        await pilot.press("enter")
        await pilot.pause()
        assert app._targets == ["google.com"]


def test_valid_config_targets_rejects_non_list():
    assert tui_mod._valid_config_targets("google.com") is None


def test_valid_config_targets_rejects_empty_list():
    assert tui_mod._valid_config_targets([]) is None


def test_valid_config_targets_cleans_whitespace_and_blanks():
    assert tui_mod._valid_config_targets([" a.test ", "", "b.test"]) == ["a.test", "b.test"]


def test_valid_refresh_interval_rejects_non_numeric():
    assert tui_mod._valid_refresh_interval("thirty") is None


def test_valid_refresh_interval_rejects_zero_or_negative():
    assert tui_mod._valid_refresh_interval(0) is None
    assert tui_mod._valid_refresh_interval(-5) is None


def test_valid_refresh_interval_accepts_positive_numeric_string():
    assert tui_mod._valid_refresh_interval("45") == 45


def test_run_tui_falls_back_on_malformed_config_targets(isolated_config, monkeypatch):
    # Simulate a hand-edited config.toml with a typo'd string instead of a
    # list -- `list("google.com")` would otherwise silently iterate
    # character-by-character into 10 single-letter "targets".
    cfg_mod.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg_mod.CONFIG_PATH.write_text('[defaults]\ntargets = "google.com"\nrefresh_interval = 30\n')

    captured = {}

    class _FakeApp:
        def __init__(self, targets, refresh):
            captured["targets"] = targets
            captured["refresh"] = refresh

        def run(self):
            pass

    monkeypatch.setattr(tui_mod, "NetHealthTUI", _FakeApp)
    tui_mod.run_tui()

    assert captured["targets"] == tui_mod._HARD_DEFAULT_TARGETS
    assert captured["refresh"] == 30  # this half of the config was fine


def test_run_tui_falls_back_on_empty_target_list(isolated_config, monkeypatch):
    cfg_mod.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg_mod.CONFIG_PATH.write_text("[defaults]\ntargets = []\nrefresh_interval = 30\n")

    captured = {}

    class _FakeApp:
        def __init__(self, targets, refresh):
            captured["targets"] = targets

        def run(self):
            pass

    monkeypatch.setattr(tui_mod, "NetHealthTUI", _FakeApp)
    tui_mod.run_tui()
    assert captured["targets"] == tui_mod._HARD_DEFAULT_TARGETS


def test_run_tui_explicit_targets_override_config(isolated_config, monkeypatch):
    captured = {}

    class _FakeApp:
        def __init__(self, targets, refresh):
            captured["targets"] = targets

        def run(self):
            pass

    monkeypatch.setattr(tui_mod, "NetHealthTUI", _FakeApp)
    tui_mod.run_tui(targets=["explicit.test"])
    assert captured["targets"] == ["explicit.test"]
