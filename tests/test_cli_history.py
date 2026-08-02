"""Unit tests for nethealth/cli.py's _save_history JSON path: the entry cap
and recovery from a corrupted history.json (both added in the robustness
batch of round 2)."""
from __future__ import annotations

import json
from pathlib import Path

from nethealth import cli as cli_mod

_RESULTS = {
    "dns": {"status": "ok"},
    "ping": {"status": "ok"},
    "http": {"status": "ok"},
    "port": {"status": "ok"},
}


def test_save_history_json_caps_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli_mod, "_MAX_HISTORY_ENTRIES", 3)

    for i in range(5):
        cli_mod._save_history(f"target{i}", _RESULTS, "json")

    history_path = tmp_path / ".nethealth" / "history.json"
    data = json.loads(history_path.read_text())
    assert len(data) == 3
    # Oldest entries dropped, most recent kept, in order.
    assert [e["target"] for e in data] == ["target2", "target3", "target4"]


def test_save_history_json_recovers_from_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    history_dir = tmp_path / ".nethealth"
    history_dir.mkdir()
    (history_dir / "history.json").write_text("not json {{{")

    path = cli_mod._save_history("target0", _RESULTS, "json")
    data = json.loads(path.read_text())
    assert len(data) == 1
    assert data[0]["target"] == "target0"


def test_save_history_json_recovers_from_non_list_root(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    history_dir = tmp_path / ".nethealth"
    history_dir.mkdir()
    (history_dir / "history.json").write_text('{"not": "a list"}')

    path = cli_mod._save_history("target0", _RESULTS, "json")
    data = json.loads(path.read_text())
    assert isinstance(data, list)
    assert len(data) == 1
