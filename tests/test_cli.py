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


@pytest.mark.parametrize(
    ("key_name", "env_name"),
    [("typesafe_api_key", "TYPESAFE_API_KEY"), ("openai_api_key", "OPENAI_API_KEY")],
)
def test_toml_api_key_is_rejected(tmp_path, monkeypatch, key_name, env_name) -> None:
    monkeypatch.delenv(env_name, raising=False)
    path = tmp_path / "jev-ff.toml"
    path.write_text(f'league_id = "L1"\n{key_name} = "secret"\n')
    with pytest.raises(ConfigError, match=env_name):
        load_settings(config_path=path)
