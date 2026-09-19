import pytest
from typer.testing import CliRunner

from jev_ff.cli import app
from jev_ff.config import load_settings
from jev_ff.errors import ConfigError

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "lineup" in result.stdout
    assert "waivers" in result.stdout
    assert "trade" in result.stdout


def test_lineup_requires_league() -> None:
    result = runner.invoke(app, ["lineup"])
    assert result.exit_code == 1
    assert "league_id" in result.output


def test_invalid_roster_id_is_a_red_error(monkeypatch) -> None:
    monkeypatch.delenv("JEV_FF_ROSTER_ID", raising=False)
    monkeypatch.delenv("SLEEPER_ROSTER_ID", raising=False)
    monkeypatch.setenv("JEV_FF_ROSTER_ID", "abc")
    result = runner.invoke(app, ["lineup", "--league-id", "L1"])
    assert result.exit_code == 1
    assert "roster" in result.output.lower()
    assert "abc" in result.output


def test_invalid_roster_id_from_env_raises_config_error(monkeypatch) -> None:
    monkeypatch.delenv("JEV_FF_ROSTER_ID", raising=False)
    monkeypatch.delenv("SLEEPER_ROSTER_ID", raising=False)
    monkeypatch.setenv("JEV_FF_ROSTER_ID", "abc")
    with pytest.raises(ConfigError, match="JEV_FF_ROSTER_ID"):
        load_settings(league_id="L1")


def test_toml_api_key_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    path = tmp_path / "jev-ff.toml"
    path.write_text('league_id = "L1"\ntypesafe_api_key = "secret"\n')
    with pytest.raises(ConfigError, match="TYPESAFE_API_KEY"):
        load_settings(config_path=path)
