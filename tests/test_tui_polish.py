"""Headless pilot tests for batch-3 TUI polish: the filter status indicator
in the health bar, sparkline panel narrowing along with the table, the
expanded Settings screen fields, and the new Help screen."""
from __future__ import annotations

import pytest
from textual.widgets import Checkbox, Input, Static

from nethealth import config as cfg_mod
from nethealth.tui import HelpScreen, NetHealthTUI, SettingsScreen


@pytest.mark.asyncio
async def test_health_bar_shows_filter_status_when_active(monkeypatch):
    app = NetHealthTUI(["google.com", "1.1.1.1", "example.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        health = app.query_one("#health-status", Static)
        # Static doesn't expose its current text as a public attribute --
        # capture what gets passed to .update() instead of reaching for a
        # private one.
        captured: list[str] = []
        monkeypatch.setattr(health, "update", lambda text, **kw: captured.append(text))

        app._filter = "goo"
        app._update_health_bar()
        assert "showing" in captured[-1]
        assert "goo" in captured[-1]

        app._filter = ""
        app._update_health_bar()
        assert "showing" not in captured[-1]


@pytest.mark.asyncio
async def test_sparkline_panel_narrows_with_filter():
    app = NetHealthTUI(["google.com", "1.1.1.1", "example.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert all(s.display for s in app._sparklines.values())

        app._filter = "goo"
        app._rebuild_table()
        assert app._sparklines["google.com"].display is True
        assert app._sparklines["1.1.1.1"].display is False
        assert app._sparklines["example.com"].display is False
        assert app._spark_labels["1.1.1.1"].display is False

        app._filter = ""
        app._rebuild_table()
        assert all(s.display for s in app._sparklines.values())


@pytest.mark.asyncio
async def test_settings_screen_has_alerts_and_speed_fields(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

        alerts_cb = app.screen.query_one("#settings-alerts-enabled", Checkbox)
        desktop_cb = app.screen.query_one("#settings-alerts-desktop", Checkbox)
        speed_input = app.screen.query_one("#settings-speed-size", Input)
        assert alerts_cb.value is True   # matches config.py defaults
        assert desktop_cb.value is True
        assert speed_input.value == "10"


@pytest.mark.asyncio
async def test_settings_save_persists_alerts_and_speed(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        app.screen.query_one("#settings-alerts-enabled", Checkbox).value = False
        app.screen.query_one("#settings-alerts-desktop", Checkbox).value = False
        app.screen.query_one("#settings-speed-size", Input).value = "25"

        await pilot.click("#settings-save")
        await pilot.pause()

        data = cfg_mod.load()
        assert data["alerts"]["enabled"] is False
        assert data["alerts"]["desktop"] is False
        assert data["speed"]["size_mb"] == 25
        # Hot-applied to the running session's alert config immediately.
        assert app._alert_cfg.get("enabled") is False


@pytest.mark.asyncio
async def test_settings_rejects_invalid_speed_size(isolated_config):
    app = NetHealthTUI(["google.com"], refresh_interval=30)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = cfg_mod.load()

        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#settings-speed-size", Input).value = "-5"

        await pilot.click("#settings-save")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert cfg_mod.load() == before


@pytest.mark.asyncio
async def test_help_screen_opens_via_question_mark_and_closes_via_escape():
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_help_screen_lists_real_bindings():
    """HelpScreen is built from the live BINDINGS list (not a hand-written
    string) specifically so it can't drift -- so this asserts the *shape*
    of that relationship rather than hard-coding specific key text, which
    would just be re-duplicating tui.py's BINDINGS list into the test."""
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()

        from textual.widgets import RichLog
        log = app.screen.query_one("#help-body", RichLog)
        described = [b for b in app.BINDINGS if getattr(b, "description", "")]
        # One written line per described binding, plus the trailing blank
        # line and the Ctrl+P hint written after the loop in on_mount.
        assert len(log.lines) >= len(described)


@pytest.mark.asyncio
async def test_help_screen_shows_plain_language_guide():
    """The Help screen leads with a jargon-light "what am I looking at"
    section before the keybindings (batch-4 ease-of-use work)."""
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()

        from textual.widgets import RichLog
        log = app.screen.query_one("#help-body", RichLog)
        text = "\n".join(str(line) for line in log.lines)
        assert "What am I looking at?" in text
        assert "Report" in text and "fills" in text
        # guide comes before the key list
        assert text.index("What am I looking at?") < text.index("Quit")


@pytest.mark.asyncio
async def test_first_run_logs_guide_hint(tmp_path, monkeypatch):
    """With no history file yet, the TUI nudges a first-time user toward `?`."""
    monkeypatch.setattr("nethealth.tui.report_mod.HISTORY_PATH", tmp_path / "nope.json")
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._first_run_hint_shown is True


@pytest.mark.asyncio
async def test_no_first_run_hint_when_history_exists(tmp_path, monkeypatch):
    hist = tmp_path / "history.json"
    hist.write_text("[]")
    monkeypatch.setattr("nethealth.tui.report_mod.HISTORY_PATH", hist)
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._first_run_hint_shown is False


@pytest.mark.asyncio
async def test_command_palette_lists_help_action():
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        titles = [c.title for c in app.get_system_commands(app.screen)]
        assert "Help / keybindings" in titles
