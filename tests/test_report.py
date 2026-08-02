"""Unit tests for nethealth/report.py -- pure aggregation over a JSON
history file, no network involved."""
from __future__ import annotations

import json

from nethealth import report as report_mod


def _write_history(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries))


def test_generate_report_empty_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, 'HISTORY_PATH', tmp_path / 'history.json')
    data = report_mod.generate_report()
    assert data['status'] == 'empty'


def test_generate_report_empty_on_corrupt_history(tmp_path, monkeypatch):
    history_path = tmp_path / 'history.json'
    history_path.write_text('not json at all {{{')
    monkeypatch.setattr(report_mod, 'HISTORY_PATH', history_path)
    data = report_mod.generate_report()
    assert data['status'] == 'empty'


def test_generate_report_aggregates_per_target(tmp_path, monkeypatch):
    history_path = tmp_path / 'history.json'
    entries = [
        {
            'timestamp': '2026-08-01T10:00:00',
            'target': 'example.com',
            'results': {
                'dns': {'status': 'ok', 'latency': 10.0},
                'ping': {'status': 'ok', 'avg_ms': 20.0},
                'http': {'status': 'ok', 'code': 200, 'latency': 100.0},
                'port': {'status': 'ok'},
            },
        },
        {
            'timestamp': '2026-08-01T10:05:00',
            'target': 'example.com',
            'results': {
                'dns': {'status': 'fail', 'error': 'timeout'},
                'ping': {'status': 'ok', 'avg_ms': 30.0},
                'http': {'status': 'ok', 'code': 200, 'latency': 120.0},
                'port': {'status': 'fail'},
            },
        },
    ]
    _write_history(history_path, entries)
    monkeypatch.setattr(report_mod, 'HISTORY_PATH', history_path)

    data = report_mod.generate_report()
    assert data['status'] == 'ok'
    assert data['entries_total'] == 2
    dns_stats = data['per_target']['example.com']['dns']
    assert dns_stats['total'] == 2
    assert dns_stats['passed'] == 1
    assert dns_stats['pass_pct'] == 50.0
    ping_stats = data['per_target']['example.com']['ping']
    assert ping_stats['avg_ms'] == 25.0
    assert ping_stats['min_ms'] == 20.0
    assert ping_stats['max_ms'] == 30.0


def test_generate_report_filters_by_target(tmp_path, monkeypatch):
    history_path = tmp_path / 'history.json'
    entries = [
        {'timestamp': '2026-08-01T10:00:00', 'target': 'a.test',
         'results': {'dns': {'status': 'ok', 'latency': 1.0}}},
        {'timestamp': '2026-08-01T10:00:00', 'target': 'b.test',
         'results': {'dns': {'status': 'ok', 'latency': 1.0}}},
    ]
    _write_history(history_path, entries)
    monkeypatch.setattr(report_mod, 'HISTORY_PATH', history_path)

    data = report_mod.generate_report(target='a.test')
    assert list(data['per_target'].keys()) == ['a.test']


def test_generate_report_last_n_limits_entries(tmp_path, monkeypatch):
    history_path = tmp_path / 'history.json'
    entries = [
        {'timestamp': f'2026-08-01T10:0{i}:00', 'target': 'a.test',
         'results': {'dns': {'status': 'ok', 'latency': float(i)}}}
        for i in range(5)
    ]
    _write_history(history_path, entries)
    monkeypatch.setattr(report_mod, 'HISTORY_PATH', history_path)

    data = report_mod.generate_report(last=2)
    assert data['entries_total'] == 2
