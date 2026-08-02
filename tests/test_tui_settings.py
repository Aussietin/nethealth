"""Headless Textual pilot tests for the in-TUI settings editor (SettingsScreen)."""
from __future__ import annotations

import pytest
from textual.widgets import Input

from nethealth import config as cfg_mod
from nethealth.tui import NetHealthTUI, SettingsScreen


@pytest.mark.asyncio
async def test_settings_save_round_trip(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

        app.screen.query_one("#settings-targets", Input).value = "one.test, two.test"
        app.screen.query_one("#settings-interval", Input).value = "45"
        app.screen.query_one("#settings-webhook", Input).value = "https://hooks.example/nethealth"

        await pilot.click("#settings-save")
        await pilot.pause()
        assert not isinstance(app.screen, SettingsScreen)

        data = cfg_mod.load()
        assert data["defaults"]["targets"] == ["one.test", "two.test"]
        assert data["defaults"]["refresh_interval"] == 45
        assert data["alerts"]["webhook_url"] == "https://hooks.example/nethealth"

        # Webhook hot-applies to the running session immediately.
        assert app._alert_cfg.get("webhook_url") == "https://hooks.example/nethealth"
        # Targets/refresh interval are next-launch-only by design (see
        # action_open_settings' docstring/comment in tui.py) -- the live
        # session keeps whatever it started with.
        assert app._refresh == 30
        assert app._targets == ["google.com"]


@pytest.mark.asyncio
async def test_settings_rejects_invalid_interval(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = cfg_mod.load()

        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#settings-interval", Input).value = "not-a-number"

        await pilot.click("#settings-save")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)  # stays open
        assert cfg_mod.load() == before  # nothing written


@pytest.mark.asyncio
async def test_settings_rejects_empty_targets(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = cfg_mod.load()

        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#settings-targets", Input).value = "   ,  ,  "

        await pilot.click("#settings-save")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert cfg_mod.load() == before


@pytest.mark.asyncio
async def test_settings_escape_cancels_without_saving(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = cfg_mod.load()

        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#settings-targets", Input).value = "changed.test"

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SettingsScreen)
        assert cfg_mod.load() == before


@pytest.mark.asyncio
async def test_settings_cancel_button_discards_changes(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = cfg_mod.load()

        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#settings-targets", Input).value = "changed.test"

        await pilot.click("#settings-cancel")
        await pilot.pause()
        assert not isinstance(app.screen, SettingsScreen)
        assert cfg_mod.load() == before


@pytest.mark.asyncio
async def test_settings_screen_surfaces_malformed_config_warning(isolated_config):
    cfg_mod.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg_mod.CONFIG_PATH.write_text("this is not [valid toml at all ===")

    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        warning = app.screen.query("#settings-warning")
        assert len(warning) == 1
