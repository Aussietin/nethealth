"""Unit tests for nethealth/checks/public_ip.py, httpx mocked out."""
from __future__ import annotations

from nethealth.checks import public_ip as ip_mod


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ip_mod.httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._payload


def test_public_ip_check_ok(monkeypatch):
    monkeypatch.setattr(
        ip_mod.httpx, "get",
        lambda url, timeout=5.0: _FakeResponse(200, {"ip": "203.0.113.5"}),
    )
    result = ip_mod.public_ip_check()
    assert result["status"] == "ok"
    assert result["ip"] == "203.0.113.5"


def test_public_ip_check_missing_ip_field(monkeypatch):
    monkeypatch.setattr(
        ip_mod.httpx, "get",
        lambda url, timeout=5.0: _FakeResponse(200, {}),
    )
    result = ip_mod.public_ip_check()
    assert result["status"] == "fail"


def test_public_ip_check_connection_error(monkeypatch):
    def _raise(url, timeout=5.0):
        raise ip_mod.httpx.ConnectError("refused")

    monkeypatch.setattr(ip_mod.httpx, "get", _raise)
    result = ip_mod.public_ip_check()
    assert result["status"] == "fail"
    assert "error" in result
