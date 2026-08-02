"""Unit tests for the pure-parsing helpers in nethealth/checks/wifi.py.
These never shell out -- they operate on canned iw/iwconfig output, so they
run identically whether or not the machine actually has a wireless card
(this WSL box doesn't)."""
from __future__ import annotations

from nethealth.checks import wifi as wifi_mod


def test_dbm_to_quality_bands():
    assert wifi_mod._dbm_to_quality(-40) == 'excellent'
    assert wifi_mod._dbm_to_quality(-50) == 'excellent'
    assert wifi_mod._dbm_to_quality(-55) == 'good'
    assert wifi_mod._dbm_to_quality(-65) == 'fair'
    assert wifi_mod._dbm_to_quality(-80) == 'poor'


def test_parse_iw_dev_finds_interfaces():
    stdout = 'phy#0\n\tInterface wlan0\n\t\tifindex 3\nphy#1\n\tInterface wlan1\n'
    assert wifi_mod._parse_iw_dev(stdout) == ['wlan0', 'wlan1']


def test_parse_iw_dev_empty_output():
    assert wifi_mod._parse_iw_dev('') == []


def test_parse_iw_link_not_connected():
    result = wifi_mod._parse_iw_link('wlan0', 'wlan0\n\tNot connected\n')
    assert result == {'interface': 'wlan0', 'connected': False}


def test_parse_iw_link_connected():
    stdout = (
        'Connected to aa:bb:cc:dd:ee:ff (on wlan0)\n'
        '\tSSID: HomeNetwork\n'
        '\tfreq: 5180\n'
        '\tsignal: -52 dBm\n'
        '\ttx bitrate: 866.7 MBit/s VHT-MCS 9\n'
        '\n'
        '\tbss flags:\tshort-slot-time\n'
        '\tRX: 12345 bytes (100 packets)\n'
    )
    result = wifi_mod._parse_iw_link('wlan0', stdout)
    assert result['connected'] is True
    assert result['ssid'] == 'HomeNetwork'
    assert result['signal_dbm'] == -52.0
    assert result['signal_quality'] == 'good'
    assert result['band'] == '5 GHz'
    assert result['tx_mbps'] == 866.7
    assert result['rx_bytes'] == 12345


def test_parse_iwconfig_connected():
    stdout = (
        'wlan0     IEEE 802.11  ESSID:"HomeNetwork"  \n'
        '          Mode:Managed  Frequency:2.437 GHz  Access Point: AA:BB:CC:DD:EE:FF   \n'
        '          Bit Rate=72.2 Mb/s   Tx-Power=20 dBm   \n'
        '          Signal level=-60 dBm  \n'
        'lo        no wireless extensions.\n'
    )
    result = wifi_mod._parse_iwconfig(stdout)
    assert result is not None
    assert result['interface'] == 'wlan0'
    assert result['ssid'] == 'HomeNetwork'
    assert result['signal_dbm'] == -60.0
    assert result['signal_quality'] == 'good'
    assert result['band'] == '2.4 GHz'
    assert result['tx_mbps'] == 72.2


def test_parse_iwconfig_no_connected_interface():
    stdout = 'lo        no wireless extensions.\neth0      no wireless extensions.\n'
    assert wifi_mod._parse_iwconfig(stdout) is None


def test_wifi_check_no_iw_no_iwconfig(monkeypatch):
    monkeypatch.setattr(wifi_mod, '_run', lambda cmd, timeout=5: (False, ''))
    result = wifi_mod.wifi_check()
    assert result['status'] == 'fail'
    assert 'iw' in result['error']
