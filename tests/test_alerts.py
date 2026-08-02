"""Unit tests for nethealth/alerts.py -- previously untested. Covers the
enabled/desktop/webhook gating in fire() and that both dispatch paths
swallow their own failures (a broken notify-send or webhook must never
raise back into the check loop that called fire())."""
from __future__ import annotations

import subprocess

from nethealth import alerts as alerts_mod


def _cfg(**overrides) -> dict:
    base = {"enabled": True, "desktop": True, "webhook_url": ""}
    base.update(overrides)
    return base


# ── fire() gating ────────────────────────────────────────────────────────

def test_fire_does_nothing_when_alerts_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append(("desktop", a)))
    monkeypatch.setattr(alerts_mod, "_webhook", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg(enabled=False, webhook_url="https://x"))
    assert calls == []


def test_fire_desktop_only_when_no_webhook_url(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append(("desktop", a)))
    monkeypatch.setattr(alerts_mod, "_webhook", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg())
    assert [c[0] for c in calls] == ["desktop"]


def test_fire_skips_desktop_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append(("desktop", a)))
    monkeypatch.setattr(alerts_mod, "_webhook", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg(desktop=False, webhook_url="https://x"))
    assert [c[0] for c in calls] == ["webhook"]


def test_fire_calls_both_when_both_configured(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append(("desktop", a)))
    monkeypatch.setattr(alerts_mod, "_webhook", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg(webhook_url="https://hooks.example/x"))
    assert [c[0] for c in calls] == ["desktop", "webhook"]


def test_fire_webhook_payload_shape(monkeypatch):
    captured = {}

    def _fake_webhook(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: None)
    monkeypatch.setattr(alerts_mod, "_webhook", _fake_webhook)

    alerts_mod.fire("example.com", "ping", "100% packet loss", _cfg(webhook_url="https://hooks.example/x"))
    assert captured["url"] == "https://hooks.example/x"
    assert captured["payload"]["target"] == "example.com"
    assert captured["payload"]["check"] == "ping"
    assert captured["payload"]["status"] == "fail"
    assert captured["payload"]["error"] == "100% packet loss"
    assert "timestamp" in captured["payload"]


def test_fire_defaults_desktop_and_enabled_true_when_keys_missing(monkeypatch):
    """cfg.get(..., True) defaults -- an old config.toml written before the
    `enabled`/`desktop` keys existed shouldn't go silent."""
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append("desktop"))
    monkeypatch.setattr(alerts_mod, "_webhook", lambda *a: calls.append("webhook"))

    alerts_mod.fire("example.com", "dns", "timeout", {})  # no keys at all
    assert calls == ["desktop"]


# ── _desktop() ───────────────────────────────────────────────────────────

def test_desktop_invokes_notify_send_with_expected_args(monkeypatch):
    captured = {}

    def _fake_run(cmd, timeout=None, capture_output=None):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(alerts_mod.subprocess, "run", _fake_run)
    alerts_mod._desktop("nethealth - DNS FAIL", "example.com: timeout")

    assert captured["cmd"][0] == "notify-send"
    assert "example.com: timeout" in captured["cmd"]
    assert "nethealth - DNS FAIL" in captured["cmd"]


def test_desktop_swallows_missing_binary(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError()

    monkeypatch.setattr(alerts_mod.subprocess, "run", _raise)
    # Must not raise -- a missing notify-send (this WSL box doesn't have
    # one) must never break the check loop that triggered the alert.
    alerts_mod._desktop("title", "body")


def test_desktop_swallows_any_subprocess_error(monkeypatch):
    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="notify-send", timeout=3)

    monkeypatch.setattr(alerts_mod.subprocess, "run", _raise)
    alerts_mod._desktop("title", "body")  # must not raise


# ── _webhook() ───────────────────────────────────────────────────────────

def test_webhook_noop_on_empty_url():
    # No httpx patch at all -- if this tried to POST it would fail (no
    # network in this call path) or hang; reaching the end proves it
    # returned early.
    alerts_mod._webhook("", {"target": "x"})


def test_webhook_posts_json_payload(monkeypatch):
    import httpx
    captured = {}

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout

    monkeypatch.setattr(httpx, "post", _fake_post)
    payload = {"target": "example.com", "check": "dns", "status": "fail"}
    alerts_mod._webhook("https://hooks.example/x", payload)

    assert captured["url"] == "https://hooks.example/x"
    assert captured["json"] == payload


def test_webhook_swallows_request_errors(monkeypatch):
    import httpx

    def _raise(url, json=None, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", _raise)
    alerts_mod._webhook("https://hooks.example/x", {"target": "x"})  # must not raise
