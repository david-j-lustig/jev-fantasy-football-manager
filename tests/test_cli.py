from typer.testing import CliRunner

from jev_ff.cli import app

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
