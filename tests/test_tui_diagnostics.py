"""Tests for batch-4 diagnostic additions surfaced in the TUI: HTTP
status-code-aware display, and the gateway status bar."""
from __future__ import annotations

import pytest
from textual.widgets import Static

import nethealth.tui as tui_mod
from nethealth.tui import NetHealthTUI, _http_display, _render_gateway_text


# ── _http_display ────────────────────────────────────────────────────────

def test_http_display_ok_2xx():
    label, ok = _http_display({"status": "ok", "code": 200})
    assert label == "200"
    assert ok is True


def test_http_display_ok_3xx_redirect_still_counts_as_ok():
    label, ok = _http_display({"status": "ok", "code": 301})
    assert ok is True


def test_http_display_4xx_shows_as_not_ok():
    label, ok = _http_display({"status": "ok", "code": 404})
    assert label == "404"
    assert ok is False


def test_http_display_5xx_shows_as_not_ok():
    label, ok = _http_display({"status": "ok", "code": 500})
    assert ok is False


def test_http_display_marks_http_fallback_scheme():
    label, ok = _http_display({"status": "ok", "code": 200, "scheme": "http"})
    assert "(http)" in label
    assert ok is True


def test_http_display_transport_failure():
    label, ok = _http_display({"status": "fail", "error": "connection refused"})
    assert label == "connection refused"
    assert ok is False


# ── Gateway bar rendering ────────────────────────────────────────────────

def test_render_gateway_text_ok():
    text = _render_gateway_text({"status": "ok", "gateway": "192.168.1.1", "avg_ms": 3.2})
    assert "192.168.1.1" in text
    assert "3 ms" in text


def test_render_gateway_text_fail():
    text = _render_gateway_text({"status": "fail", "error": "no route"})
    assert "no route" in text
    assert "red" in text  # styled as a problem, not just dim


@pytest.mark.asyncio
async def test_gateway_bar_updates_on_mount(monkeypatch):
    monkeypatch.setattr(
        tui_mod, "gateway_check",
        lambda: {"status": "ok", "gateway": "10.0.0.1", "avg_ms": 1.0},
    )
    app = NetHealthTUI(["google.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        gw_static = app.query_one("#gateway-status", Static)
        assert gw_static is not None  # widget exists and mounted without error


# ── Health bar honours http_display semantics ───────────────────────────

@pytest.mark.asyncio
async def test_health_bar_excludes_target_with_http_error_code(monkeypatch):
    app = NetHealthTUI(["example.com"], refresh_interval=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        health = app.query_one("#health-status", Static)
        captured: list[str] = []
        monkeypatch.setattr(health, "update", lambda text, **kw: captured.append(text))

        ok = {"status": "ok"}
        app._update_ui(
            "example.com",
            dict(ok, latency=5),
            dict(ok, avg_ms=5.0),
            dict(ok, code=500),  # HTTP "succeeded" but server errored
            dict(ok, results=[{"port": 443, "status": "open"}]),
            dict(ok, days_left=90),
        )
        assert "0/1 healthy" in captured[-1]
