"""History persistence through `check --save` (nethealth.report.record_check):
the entry cap and recovery from a corrupted history.json."""
from __future__ import annotations

import json

from nethealth import cli as cli_mod
from nethealth import report as report_mod

_RESULTS = {
    "dns": {"status": "ok"},
    "ping": {"status": "ok"},
    "http": {"status": "ok"},
    "port": {"status": "ok"},
}


def test_save_history_json_caps_entries(monkeypatch):
    monkeypatch.setattr(report_mod, "MAX_HISTORY_ENTRIES", 3)

    for i in range(5):
        cli_mod._save_history(f"target{i}", _RESULTS, "json")

    data = json.loads(report_mod.HISTORY_PATH.read_text())
    # Oldest entries dropped, most recent kept, in order.
    assert [e["target"] for e in data] == ["target2", "target3", "target4"]


def test_save_history_json_moves_corrupt_file_aside():
    path = report_mod.HISTORY_PATH
    path.write_text("not json {{{")

    cli_mod._save_history("target0", _RESULTS, "json")
    data = json.loads(path.read_text())
    assert [e["target"] for e in data] == ["target0"]
    # The unreadable original is kept, not overwritten.
    aside = list(path.parent.glob("history.json.corrupt-*"))
    assert len(aside) == 1 and aside[0].read_text() == "not json {{{"


def test_save_history_json_recovers_from_non_list_root():
    report_mod.HISTORY_PATH.write_text('{"not": "a list"}')

    cli_mod._save_history("target0", _RESULTS, "json")
    data = json.loads(report_mod.HISTORY_PATH.read_text())
    assert isinstance(data, list) and len(data) == 1
