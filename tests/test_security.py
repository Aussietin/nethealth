from __future__ import annotations

from nethealth.checks import security as security_mod


def test_headers_reports_missing_defences(monkeypatch):
    class Response:
        headers = {"server": "example"}
        url = "https://example.com/"
        status_code = 200

    monkeypatch.setattr(security_mod.httpx, "head", lambda *args, **kwargs: Response())
    result = security_mod.http_security_headers_check("example.com")

    assert result["status"] == "ok"
    titles = {finding["title"] for finding in result["findings"]}
    assert "HSTS header is missing" in titles
    assert "Clickjacking protection is missing" in titles


def test_headers_accepts_csp_frame_ancestors(monkeypatch):
    class Response:
        headers = {
            "strict-transport-security": "max-age=31536000",
            "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
            "x-content-type-options": "nosniff",
            "referrer-policy": "strict-origin-when-cross-origin",
        }
        url = "https://example.com/"
        status_code = 200

    monkeypatch.setattr(security_mod.httpx, "head", lambda *args, **kwargs: Response())
    result = security_mod.http_security_headers_check("example.com")

    assert result["findings"] == []


def test_audit_flags_reachable_remote_services(monkeypatch):
    monkeypatch.setattr(
        security_mod, "port_check",
        lambda *args, **kwargs: {"results": [
            {"port": 22, "status": "open"}, {"port": 3389, "status": "open"},
            {"port": 443, "status": "closed"},
        ]},
    )
    result = security_mod.security_audit("host.example", ports=[22, 3389, 443])

    assert result["status"] == "warn"
    assert result["tls"] is None
    assert {item["title"] for item in result["findings"]} == {
        "SSH service is reachable", "Remote Desktop is reachable",
    }


def test_audit_includes_tls_and_header_findings(monkeypatch):
    monkeypatch.setattr(security_mod, "port_check", lambda *args, **kwargs: {"results": [{"port": 443, "status": "open"}]})
    monkeypatch.setattr(security_mod, "ssl_check", lambda *args, **kwargs: {"status": "ok", "days_left": 10})
    monkeypatch.setattr(
        security_mod, "http_security_headers_check",
        lambda *args, **kwargs: {"findings": [
            {"severity": "warn", "title": "HSTS header is missing", "detail": "set it", "category": "http"},
        ]},
    )
    result = security_mod.security_audit("host.example", ports=[443])

    assert result["status"] == "warn"
    assert {item["title"] for item in result["findings"]} == {
        "TLS certificate expires soon", "HSTS header is missing",
    }
