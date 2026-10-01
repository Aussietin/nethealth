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
    monkeypatch.setattr(alerts_mod, "_post", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg(enabled=False, webhook_url="https://x"))
    assert calls == []


def test_fire_desktop_only_when_no_webhook_url(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append(("desktop", a)))
    monkeypatch.setattr(alerts_mod, "_post", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg())
    assert [c[0] for c in calls] == ["desktop"]


def test_fire_skips_desktop_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append(("desktop", a)))
    monkeypatch.setattr(alerts_mod, "_post", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg(desktop=False, webhook_url="https://x"))
    assert [c[0] for c in calls] == ["webhook"]


def test_fire_calls_both_when_both_configured(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: calls.append(("desktop", a)))
    monkeypatch.setattr(alerts_mod, "_post", lambda *a: calls.append(("webhook", a)))

    alerts_mod.fire("example.com", "dns", "timeout", _cfg(webhook_url="https://hooks.example/x"))
    assert [c[0] for c in calls] == ["desktop", "webhook"]


def test_fire_webhook_payload_shape(monkeypatch):
    captured = {}

    def _fake_webhook(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: None)
    monkeypatch.setattr(alerts_mod, "_post", _fake_webhook)

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
    monkeypatch.setattr(alerts_mod, "_post", lambda *a: calls.append("webhook"))

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


def test_desktop_passes_text_to_osascript_as_argv(monkeypatch):
    """Title/body go in argv, never into the AppleScript source -- an error
    string with a double quote used to break (or inject into) the script."""
    captured = {}

    def _fake_run(cmd, timeout=None, capture_output=None):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(alerts_mod.sys, "platform", "darwin")
    monkeypatch.setattr(alerts_mod.subprocess, "run", _fake_run)
    body = 'example.com: bad "quoted" error'
    alerts_mod._desktop("nethealth - DNS FAIL", body)

    cmd = captured["cmd"]
    assert cmd[0] == "osascript"
    assert cmd[-2:] == ["nethealth - DNS FAIL", body]
    script = " ".join(cmd[1:-2])
    assert "quoted" not in script


# ── _post() and the webhook body builders ────────────────────────────────

_PAYLOAD = {"target": "example.com", "check": "dns", "status": "fail",
            "error": "timeout", "timestamp": "2026-09-05T10:00:00"}


def test_post_sends_json(monkeypatch):
    import httpx
    captured = {}

    def _fake_post(url, json=None, timeout=None):
        captured.update(url=url, json=json, timeout=timeout)

    monkeypatch.setattr(httpx, "post", _fake_post)
    alerts_mod._post("https://hooks.example/x", {"a": 1})
    assert captured == {"url": "https://hooks.example/x", "json": {"a": 1}, "timeout": 5}


def test_post_swallows_request_errors(monkeypatch):
    import httpx

    def _raise(url, json=None, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", _raise)
    alerts_mod._post("https://hooks.example/x", {"target": "x"})  # must not raise


def test_slack_body_is_formatted_text():
    text = alerts_mod._slack_body(_PAYLOAD)["text"]
    assert "example.com" in text and "DNS" in text


def test_teams_body_is_message_card():
    card = alerts_mod._teams_body(_PAYLOAD)
    assert card["@type"] == "MessageCard"
    assert card["summary"].startswith("nethealth")


def test_fire_routes_each_configured_webhook(monkeypatch):
    posts = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: None)
    monkeypatch.setattr(alerts_mod, "_post", lambda url, body: posts.append((url, body)))

    cfg = _cfg(webhook_url="https://generic.example/x",
               slack_webhook_url="https://hooks.slack.example/x",
               teams_webhook_url="https://outlook.office.com/webhook/x")
    alerts_mod.fire("example.com", "dns", "timeout", cfg)

    by_url = dict(posts)
    assert by_url["https://generic.example/x"]["target"] == "example.com"
    assert "text" in by_url["https://hooks.slack.example/x"]
    assert by_url["https://outlook.office.com/webhook/x"]["@type"] == "MessageCard"


def test_fire_skips_unconfigured_webhooks(monkeypatch):
    posts = []
    monkeypatch.setattr(alerts_mod, "_desktop", lambda *a: None)
    monkeypatch.setattr(alerts_mod, "_post", lambda *a: posts.append(a))
    alerts_mod.fire("example.com", "dns", "timeout", _cfg())
    assert posts == []
