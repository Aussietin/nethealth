"""Unit tests for nethealth/config.py -- load/save/malformed-file handling.
No network access needed; everything runs against isolated_config's tmp dir.
"""
from __future__ import annotations

from nethealth import config as cfg_mod


def test_load_creates_default_file_on_first_run(isolated_config):
    assert not cfg_mod.CONFIG_PATH.exists()
    data = cfg_mod.load()
    assert cfg_mod.CONFIG_PATH.exists()
    assert data['defaults']['targets'] == ['google.com', '1.1.1.1']
    assert data['defaults']['refresh_interval'] == 30
    assert data['alerts']['webhook_url'] == ''
    assert data['speed']['size_mb'] == 10


def test_defaults_and_alert_cfg_helpers(isolated_config):
    assert cfg_mod.defaults() == cfg_mod.load()['defaults']
    assert cfg_mod.alert_cfg() == cfg_mod.load()['alerts']


def test_load_with_status_no_error_on_valid_file(isolated_config):
    data, error = cfg_mod.load_with_status()
    assert error is None
    assert data['defaults']['targets'] == ['google.com', '1.1.1.1']


def test_save_round_trip(isolated_config):
    cfg_mod.load()
    new_data = {
        'defaults': {'targets': ['a.test', 'b.test'], 'refresh_interval': 45},
        'alerts': {'enabled': False, 'desktop': True, 'webhook_url': 'https://hooks.example/x'},
        'speed': {'size_mb': 25},
    }
    cfg_mod.save(new_data)

    reloaded = cfg_mod.load()
    assert reloaded['defaults']['targets'] == ['a.test', 'b.test']
    assert reloaded['defaults']['refresh_interval'] == 45
    assert reloaded['alerts']['enabled'] is False
    assert reloaded['alerts']['webhook_url'] == 'https://hooks.example/x'
    assert reloaded['speed']['size_mb'] == 25


def test_save_preserves_comment_template_structure(isolated_config):
    cfg_mod.load()
    cfg_mod.save({
        'defaults': {'targets': ['x.test'], 'refresh_interval': 10},
        'alerts': {'enabled': True, 'desktop': True, 'webhook_url': ''},
        'speed': {'size_mb': 10},
    })
    text = cfg_mod.CONFIG_PATH.read_text()
    assert '[defaults]' in text
    assert '[alerts]' in text
    assert '[speed]' in text
    assert '# Targets the TUI monitors' in text


def test_malformed_toml_falls_back_to_defaults(isolated_config):
    cfg_mod.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg_mod.CONFIG_PATH.write_text('this is not [valid toml at all ===')

    data, error = cfg_mod.load_with_status()
    assert error is not None
    assert data['defaults']['targets'] == ['google.com', '1.1.1.1']

    data2 = cfg_mod.load()
    assert data2['defaults']['refresh_interval'] == 30


def test_save_with_empty_targets_falls_back(isolated_config):
    cfg_mod.load()
    cfg_mod.save({
        'defaults': {'targets': [], 'refresh_interval': 30},
        'alerts': {'enabled': True, 'desktop': True, 'webhook_url': ''},
        'speed': {'size_mb': 10},
    })
    reloaded = cfg_mod.load()
    assert reloaded['defaults']['targets'] == ['google.com', '1.1.1.1']
