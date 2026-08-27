"""Shared pytest fixtures for the nethealth test suite.

Nothing here touches Austin's real ~/.nethealth — every test that reads or
writes config goes through the isolated_config fixture, which points the
nethealth.config module (and anything that imported it, e.g. nethealth.tui)
at a throwaway directory under pytest's tmp_path.
"""
from __future__ import annotations

import pytest

from nethealth import config as cfg_mod
from nethealth import report as report_mod


@pytest.fixture(autouse=True)
def _isolate_history(tmp_path, monkeypatch):
    """No test may touch Austin's real ~/.nethealth/history.json. The TUI
    monitor loop now records snapshots there (see tui._maybe_record_history),
    so this guard is autouse rather than opt-in."""
    monkeypatch.setattr(report_mod, "HISTORY_PATH", tmp_path / "history.json")


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point nethealth.config at a throwaway config dir for this test only."""
    config_dir = tmp_path / ".nethealth"
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", config_dir / "config.toml")
    return config_dir
