"""Unit tests for the individual check functions with the network/subprocess
layer mocked out -- deterministic, no real DNS/HTTP/socket/ping calls, so
these run the same offline as they do with a live connection."""
from __future__ import annotations

import socket
import subprocess

import pytest

from nethealth.checks import dns as dns_mod
from nethealth.checks import http as http_mod
from nethealth.checks import port as port_mod
from nethealth.checks import ping as ping_mod


# ── DNS ──────────────────────────────────────────────────────────────────

def test_dns_check_ok(monkeypatch):
    monkeypatch.setattr(dns_mod.dns.resolver, 'resolve', lambda host, rtype: object())
    result = dns_mod.dns_check('example.com')
    assert result['status'] == 'ok'
    assert result['latency'] >= 0


def test_dns_check_fail(monkeypatch):
    def _raise(host, rtype):
        raise dns_mod.dns.resolver.NXDOMAIN()
    monkeypatch.setattr(dns_mod.dns.resolver, 'resolve', _raise)
    result = dns_mod.dns_check('doesnotexist.invalid')
    assert result['status'] == 'fail'
    assert 'error' in result


# ── HTTP ─────────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_http_check_ok(monkeypatch):
    monkeypatch.setattr(http_mod.httpx, 'get', lambda url, timeout=5.0: _FakeResponse(200))
    result = http_mod.http_check('example.com')
    assert result['status'] == 'ok'
    assert result['code'] == 200
    assert result['latency'] >= 0


def test_http_check_uses_https_scheme(monkeypatch):
    seen = {}

    def _fake_get(url, timeout=5.0):
        seen['url'] = url
        return _FakeResponse(200)

    monkeypatch.setattr(http_mod.httpx, 'get', _fake_get)
    http_mod.http_check('example.com')
    assert seen['url'] == 'https://example.com'


def test_http_check_connection_error(monkeypatch):
    def _raise(url, timeout=5.0):
        raise http_mod.httpx.ConnectError('refused')

    monkeypatch.setattr(http_mod.httpx, 'get', _raise)
    result = http_mod.http_check('unreachable.invalid')
    assert result['status'] == 'fail'
    assert 'error' in result


def test_http_check_falls_back_to_http_on_connect_error(monkeypatch):
    """A LAN device with no TLS at all (router, printer, IoT gear) should
    still show reachable via the http:// fallback instead of always FAIL."""
    calls = []

    def _fake_get(url, timeout=5.0):
        calls.append(url)
        if url.startswith('https://'):
            raise http_mod.httpx.ConnectError('refused')
        return _FakeResponse(200)

    monkeypatch.setattr(http_mod.httpx, 'get', _fake_get)
    result = http_mod.http_check('router.lan')
    assert result['status'] == 'ok'
    assert result['scheme'] == 'http'
    assert calls == ['https://router.lan', 'http://router.lan']


def test_http_check_does_not_fall_back_on_non_connect_error(monkeypatch):
    """Only a connection-level failure triggers the http:// retry -- a
    timeout or any other RequestError should fail straight away rather
    than doubling every slow check's latency."""
    calls = []

    def _fake_get(url, timeout=5.0):
        calls.append(url)
        raise http_mod.httpx.ReadTimeout('slow')

    monkeypatch.setattr(http_mod.httpx, 'get', _fake_get)
    result = http_mod.http_check('slow.example')
    assert result['status'] == 'fail'
    assert calls == ['https://slow.example']


def test_http_check_reports_https_error_when_both_schemes_fail(monkeypatch):
    def _fake_get(url, timeout=5.0):
        raise http_mod.httpx.ConnectError(f'refused: {url}')

    monkeypatch.setattr(http_mod.httpx, 'get', _fake_get)
    result = http_mod.http_check('dead.invalid')
    assert result['status'] == 'fail'
    assert 'https://dead.invalid' in result['error']


# ── Port ─────────────────────────────────────────────────────────────────

def test_port_check_open(monkeypatch):
    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(port_mod.socket, 'create_connection', lambda addr, timeout: _FakeConn())
    result = port_mod.port_check('example.com', ports=[443])
    assert result['status'] == 'ok'
    assert result['results'] == [{'port': 443, 'status': 'open'}]


def test_port_check_closed(monkeypatch):
    def _raise(addr, timeout):
        raise ConnectionRefusedError()

    monkeypatch.setattr(port_mod.socket, 'create_connection', _raise)
    result = port_mod.port_check('example.com', ports=[9999])
    assert result['status'] == 'fail'
    assert result['results'] == [{'port': 9999, 'status': 'closed'}]


def test_port_check_default_ports_used_when_none_given(monkeypatch):
    monkeypatch.setattr(
        port_mod.socket, 'create_connection',
        lambda addr, timeout: (_ for _ in ()).throw(socket.timeout()),
    )
    result = port_mod.port_check('example.com')
    checked_ports = [r['port'] for r in result['results']]
    assert checked_ports == [22, 80, 443]


def test_port_check_probes_concurrently_not_sequentially(monkeypatch):
    """Each simulated port takes 0.3s to time out. Checked sequentially,
    5 ports would take >=1.5s; checked concurrently (the whole point of
    ThreadPoolExecutor in port_check) it should take roughly one slot,
    not five. Generous threshold to avoid CI-timing flakiness -- this is
    checking "clearly parallel" not measuring exact wall time."""
    import time

    def _slow_timeout(addr, timeout):
        time.sleep(0.3)
        raise socket.timeout()

    monkeypatch.setattr(port_mod.socket, 'create_connection', _slow_timeout)
    start = time.time()
    result = port_mod.port_check('example.com', ports=[10001, 10002, 10003, 10004, 10005])
    elapsed = time.time() - start

    assert len(result['results']) == 5
    assert elapsed < 1.0  # would be >=1.5s if sequential


def test_port_check_preserves_input_order_under_concurrency(monkeypatch):
    """executor.map preserves input order regardless of which port's probe
    finishes first -- vary the fake per-port delay to actually exercise
    that (rather than every mock returning instantly, which wouldn't
    prove ordering survives out-of-order completion)."""
    import time

    def _variable_delay(addr, timeout):
        port = addr[1]
        # Higher port numbers "finish" first.
        time.sleep(0.05 * (10005 - port) / 1000)
        raise socket.timeout()

    monkeypatch.setattr(port_mod.socket, 'create_connection', _variable_delay)
    ports = [10001, 10002, 10003, 10004, 10005]
    result = port_mod.port_check('example.com', ports=ports)
    assert [r['port'] for r in result['results']] == ports


# ── Ping ─────────────────────────────────────────────────────────────────

def test_ping_check_ok(monkeypatch):
    fake_proc = subprocess.CompletedProcess(
        args=['ping'], returncode=0,
        stdout='rtt min/avg/max/mdev = 10.0/15.5/20.0/2.0 ms\n', stderr='',
    )
    monkeypatch.setattr(ping_mod.subprocess, 'run', lambda *a, **kw: fake_proc)
    result = ping_mod.ping_check('example.com')
    assert result['status'] == 'ok'
    assert result['avg_ms'] == 15.5


def test_ping_check_command_not_found(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError()

    monkeypatch.setattr(ping_mod.subprocess, 'run', _raise)
    result = ping_mod.ping_check('example.com')
    assert result['status'] == 'fail'
    assert 'not found' in result['error'].lower()


def test_ping_check_nonzero_exit(monkeypatch):
    fake_proc = subprocess.CompletedProcess(
        args=['ping'], returncode=1, stdout='', stderr='Name or service not known',
    )
    monkeypatch.setattr(ping_mod.subprocess, 'run', lambda *a, **kw: fake_proc)
    result = ping_mod.ping_check('doesnotexist.invalid')
    assert result['status'] == 'fail'
