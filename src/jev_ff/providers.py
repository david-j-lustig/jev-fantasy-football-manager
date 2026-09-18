"""Swappable data providers for projections and news."""

from __future__ import annotations

from typing import Protocol

from jev_ff.sleeper.client import SleeperClient
from jev_ff.sleeper.models import Player, Projection


class ProjectionsProvider(Protocol):
    def weekly(self, season: str, week: int, *, season_type: str = "regular") -> dict[str, Projection]:
        """player_id -> weekly projection."""

    def rest_of_season(self, season: str, *, season_type: str = "regular") -> dict[str, Projection]:
        """player_id -> season-long (ROS-ish) projection."""


class NewsProvider(Protocol):
    def headlines(self, player: Player, *, week: int) -> list[str]:
        """Short notes Jev can read. Empty is fine."""


class SleeperProjectionsProvider:
    def __init__(self, client: SleeperClient) -> None:
        self.client = client

    def weekly(self, season: str, week: int, *, season_type: str = "regular") -> dict[str, Projection]:
        return self.client.get_projections(season, week, season_type=season_type)

    def rest_of_season(self, season: str, *, season_type: str = "regular") -> dict[str, Projection]:
        return self.client.get_projections(season, season_type=season_type)


class InjuryNewsProvider:
    """Default news: Sleeper injury fields only."""

    def headlines(self, player: Player, *, week: int) -> list[str]:
        notes: list[str] = []
        if player.injury_status:
            notes.append(f"Injury status: {player.injury_status}")
        if player.practice_participation:
            notes.append(f"Practice: {player.practice_participation}")
        if player.injury_notes:
            notes.append(player.injury_notes)
        return notes
