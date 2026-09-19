"""Bye-week helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from jev_ff.sleeper.models import Player, Projection

NFL_TEAMS = {
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LAC",
    "LAR",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
}

OUT_STATUSES = {"Out", "IR", "PUP", "Suspended", "NA", "COV", "Covid", "Inactive"}


def bye_teams_from_schedule(schedule: Iterable[dict[str, Any]], week: int) -> set[str]:
    playing: set[str] = set()
    for game in schedule:
        if int(game.get("week") or 0) != week:
            continue
        for key in ("home", "away", "home_team", "away_team"):
            team = game.get(key)
            if isinstance(team, str) and team:
                playing.add(team.upper())
        teams = game.get("teams")
        if isinstance(teams, list):
            playing.update(str(team).upper() for team in teams)
    if not playing:
        return set()
    return {team for team in NFL_TEAMS if team not in playing}


def bye_teams_from_projections(
    projections: Mapping[str, Projection],
    players: Mapping[str, Player],
) -> set[str]:
    playing: set[str] = set()
    for player_id, projection in projections.items():
        opponent = (projection.opponent or "").upper()
        if opponent in {"", "BYE", "NONE"}:
            continue
        player = players.get(player_id)
        if player and player.team:
            playing.add(player.team.upper())
        if opponent in NFL_TEAMS:
            playing.add(opponent)
    if len(playing) < 16:
        return set()
    return {team for team in NFL_TEAMS if team not in playing}


def is_on_bye(player: Player, bye_teams: set[str], projection: Projection | None) -> bool:
    if player.team and player.team.upper() in bye_teams:
        return True
    if projection is not None and (projection.opponent or "").upper() in {"BYE"}:
        return True
    return False


def is_out(player: Player) -> bool:
    status = (player.injury_status or "").strip()
    return status in OUT_STATUSES
