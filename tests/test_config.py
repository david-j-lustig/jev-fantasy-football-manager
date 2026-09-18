from jev_ff.config import load_settings


def test_load_from_toml(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JEV_FF_LEAGUE_ID", raising=False)
    monkeypatch.delenv("SLEEPER_LEAGUE_ID", raising=False)
    path = tmp_path / "jev-ff.toml"
    path.write_text('league_id = "999"\nroster_id = 2\nmodel = "jev-1.13.0"\n')
    settings = load_settings(config_path=path)
    assert settings.league_id == "999"
    assert settings.roster_id == 2
    assert settings.model == "jev-1.13.0"


def test_cli_overrides_toml(tmp_path) -> None:
    path = tmp_path / "jev-ff.toml"
    path.write_text('league_id = "999"\nroster_id = 2\n')
    settings = load_settings(league_id="111", roster_id=7, config_path=path)
    assert settings.league_id == "111"
    assert settings.roster_id == 7
