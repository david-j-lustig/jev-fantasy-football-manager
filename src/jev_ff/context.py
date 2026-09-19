"""Loaded league snapshot used by lineup, waiver, and trade features."""

from __future__ import annotations

from dataclasses import dataclass, field

from jev_ff.errors import ConfigError, SleeperError
from jev_ff.sleeper.models import League, Player, Projection, Roster, User
from jev_ff.sleeper.scoring import league_points


@dataclass
class LeagueContext:
    league: League
    rosters: list[Roster]
    users: list[User]
    players: dict[str, Player]
    week: int
    season: str
    season_type: str
    weekly_projections: dict[str, Projection] = field(default_factory=dict)
    season_projections: dict[str, Projection] = field(default_factory=dict)
    weekly_stats: dict[str, dict] = field(default_factory=dict)
    trending: dict[str, int] = field(default_factory=dict)
    bye_teams: set[str] = field(default_factory=set)
    headlines: dict[str, list[str]] = field(default_factory=dict)

    @property
    def scoring_settings(self) -> dict[str, float]:
        return self.league.scoring_settings

    def week_points(self) -> dict[str, float]:
        return {
            player_id: league_points(projection.stats, self.scoring_settings)
            for player_id, projection in self.weekly_projections.items()
        }

    def ros_points(self) -> dict[str, float]:
        return {
            player_id: league_points(projection.stats, self.scoring_settings)
            for player_id, projection in self.season_projections.items()
        }

    def opponents(self) -> dict[str, str | None]:
        return {player_id: projection.opponent for player_id, projection in self.weekly_projections.items()}

    def roster(self, roster_id: int) -> Roster:
        for item in self.rosters:
            if item.roster_id == roster_id:
                return item
        raise ConfigError(f"Roster {roster_id} not in league {self.league.league_id}.")

    def user_for_roster(self, roster: Roster) -> User | None:
        for user in self.users:
            if user.user_id == roster.owner_id:
                return user
        return None

    def roster_players(self, roster: Roster) -> list[Player]:
        missing = [player_id for player_id in roster.players if player_id not in self.players]
        if missing:
            shown = ", ".join(missing[:8])
            extra = "" if len(missing) <= 8 else f" (+{len(missing) - 8} more)"
            raise SleeperError(
                f"{len(missing)} rostered player(s) missing from the Sleeper player map: {shown}{extra}. "
                "The player cache may be stale; delete ~/.cache/jev_ff/players_nfl.json and retry."
            )
        return [self.players[player_id] for player_id in roster.players]
