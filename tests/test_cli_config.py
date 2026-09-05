"""CLI tests for `nethealth config show/edit/reset`."""
from __future__ import annotations

from click.testing import CliRunner

from nethealth.cli import cli


def test_config_show_creates_and_prints_defaults(isolated_config):
    result = CliRunner().invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "targets" in result.output
    assert "google.com" in result.output
    assert "webhook_url" in result.output
    assert "slack_webhook_url" in result.output
    assert "teams_webhook_url" in result.output


def test_config_show_reports_parse_error_and_falls_back(isolated_config):
    isolated_config.mkdir(parents=True, exist_ok=True)
    (isolated_config / "config.toml").write_text("not = [valid toml")
    result = CliRunner().invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "error" in result.output.lower() or "⚠" in result.output


def test_config_reset_requires_confirmation_without_yes(isolated_config):
    result = CliRunner().invoke(cli, ["config", "reset"], input="n\n")
    assert not isolated_config.joinpath("config.toml").exists() or result.exit_code != 0


def test_config_reset_with_yes_writes_defaults(isolated_config):
    isolated_config.mkdir(parents=True, exist_ok=True)
    (isolated_config / "config.toml").write_text("garbage")
    result = CliRunner().invoke(cli, ["config", "reset", "--yes"])
    assert result.exit_code == 0
    content = (isolated_config / "config.toml").read_text()
    assert "google.com" in content
    assert "slack_webhook_url" in content


def test_config_edit_reports_missing_editor(isolated_config, monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setattr(
        "nethealth.cli.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    result = CliRunner().invoke(cli, ["config", "edit"])
    assert result.exit_code == 0
    assert "Could not launch" in result.output
    assert isolated_config.joinpath("config.toml").exists()
