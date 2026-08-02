"""Headless Textual pilot tests for the Monitor tab's filter/search feature.

Uses app.run_test() + Pilot, the pattern this codebase already relies on --
it's what caught the _render name collision and the call_from_thread misuse
during the 2026-07-27 TUI rewrite (see the vault note for that history).
"""
from __future__ import annotations

import pytest
from textual.widgets import DataTable, Input

from nethealth.tui import NetHealthTUI


@pytest.mark.asyncio
async def test_filter_narrows_table_live():
    app = NetHealthTUI(["google.com", "1.1.1.1", "example.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(DataTable)
        assert table.row_count == 3

        filt = app.query_one("#filter-input", Input)
        assert filt.display is False

        await pilot.press("slash")
        await pilot.pause()
        assert filt.display is True
        assert app.focused is filt

        await pilot.press("g", "o", "o")
        await pilot.pause()
        assert app._filter == "goo"
        assert table.row_count == 1
        row_key, _ = table.coordinate_to_cell_key((0, 0))
        assert row_key.value == "google.com"


@pytest.mark.asyncio
async def test_escape_clears_filter_and_restores_rows():
    app = NetHealthTUI(["google.com", "1.1.1.1", "example.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(DataTable)
        filt = app.query_one("#filter-input", Input)

        await pilot.press("slash")
        await pilot.press("g", "o", "o")
        await pilot.pause()
        assert table.row_count == 1

        await pilot.press("escape")
        await pilot.pause()
        assert app._filter == ""
        assert filt.display is False
        assert table.row_count == 3


@pytest.mark.asyncio
async def test_filtered_out_target_keeps_updating_in_background():
    """A target hidden by the filter must not crash _update_ui, and its
    latest results must still be cached for when the filter is cleared."""
    app = NetHealthTUI(["google.com", "1.1.1.1"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._filter = "goo"
        app._rebuild_table()
        table = app.query_one(DataTable)
        assert table.row_count == 1

        ok = {"status": "ok"}
        app._update_ui(
            "1.1.1.1",
            dict(ok, latency=5),
            dict(ok, avg_ms=5.0),
            dict(ok, code=200),
            dict(ok, results=[{"port": 443, "status": "open"}]),
            dict(ok, days_left=90),
        )
        assert "1.1.1.1" in app._latest
        assert table.row_count == 1  # still hidden -- not added to the table

        app._filter = ""
        app._rebuild_table()
        assert table.row_count == 2
        # Cached cells from the background update should show real data,
        # not a stale "checking..." placeholder.
        row_key, _ = table.coordinate_to_cell_key((1, 0))
        assert row_key.value == "1.1.1.1"


@pytest.mark.asyncio
async def test_add_target_while_filtered_stays_hidden_but_monitored():
    app = NetHealthTUI(["alpha.example", "beta.example"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(DataTable)

        app._filter = "alpha"
        app._rebuild_table()
        assert table.row_count == 1

        app._targets.append("gamma.example")
        app._latency["gamma.example"]
        app._mount_sparkline("gamma.example")
        app._rebuild_table()

        assert table.row_count == 1  # gamma doesn't match "alpha"
        assert "gamma.example" in app._targets  # but it's still tracked

        app._filter = ""
        app._rebuild_table()
        assert table.row_count == 3


@pytest.mark.asyncio
async def test_command_palette_lists_filter_and_settings_actions():
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        titles = [c.title for c in app.get_system_commands(app.screen)]
        assert "Filter targets" in titles
        assert "Settings" in titles
        # "Clear filter" only makes sense (and only appears) once a filter
        # is actually active.
        assert "Clear filter" not in titles
        app._filter = "goo"
        titles_filtered = [c.title for c in app.get_system_commands(app.screen)]
        assert "Clear filter" in titles_filtered
