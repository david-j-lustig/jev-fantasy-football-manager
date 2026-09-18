"""Load league/roster settings from env, CLI flags, and jev-ff.toml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jev_ff.errors import ConfigError

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class Settings:
    league_id: str
    roster_id: int | None = None
    username: str | None = None
    typesafe_api_key: str | None = None
    model: str = "jev-latest"
    week: int | None = None


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def discover_config_path(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        if not explicit.exists():
            raise ConfigError(f"Config file not found: {explicit}")
        return explicit
    candidates = [
        Path.cwd() / "jev-ff.toml",
        Path.home() / ".config" / "jev-ff" / "config.toml",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_settings(
    *,
    league_id: str | None = None,
    roster_id: int | None = None,
    username: str | None = None,
    typesafe_api_key: str | None = None,
    model: str | None = None,
    week: int | None = None,
    config_path: Path | None = None,
) -> Settings:
    file_data: dict[str, Any] = {}
    found = discover_config_path(config_path)
    if found is not None:
        file_data = load_toml(found)

    resolved_league = (
        league_id
        or os.environ.get("JEV_FF_LEAGUE_ID")
        or os.environ.get("SLEEPER_LEAGUE_ID")
        or _as_str(file_data.get("league_id"))
    )
    if not resolved_league:
        raise ConfigError("league_id is required. Pass --league-id, set JEV_FF_LEAGUE_ID, or add it to jev-ff.toml.")

    env_roster = os.environ.get("JEV_FF_ROSTER_ID") or os.environ.get("SLEEPER_ROSTER_ID")
    resolved_roster = roster_id
    if resolved_roster is None and env_roster:
        resolved_roster = int(env_roster)
    if resolved_roster is None and file_data.get("roster_id") is not None:
        resolved_roster = int(file_data["roster_id"])

    resolved_username = (
        username
        or os.environ.get("SLEEPER_USER")
        or os.environ.get("JEV_FF_USERNAME")
        or _as_str(file_data.get("username"))
    )
    resolved_key = (
        typesafe_api_key
        or os.environ.get("TYPESAFE_API_KEY")
        or os.environ.get("JEV_API_KEY")
        or _as_str(file_data.get("typesafe_api_key"))
    )
    resolved_model = model or os.environ.get("JEV_FF_MODEL") or _as_str(file_data.get("model")) or "jev-latest"
    return Settings(
        league_id=resolved_league,
        roster_id=resolved_roster,
        username=resolved_username,
        typesafe_api_key=resolved_key,
        model=resolved_model,
        week=week,
    )


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
