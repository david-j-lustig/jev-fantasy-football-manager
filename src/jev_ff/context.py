"""Loaded league snapshot used by lineup, waiver, and trade features."""

from __future__ import annotations

from dataclasses import dataclass, field

from jev_ff.sleeper.models import League, NFLState, Player, Projection, Roster, User
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
        return {pid: league_points(proj.stats, self.scoring_settings) for pid, proj in self.weekly_projections.items()}

    def ros_points(self) -> dict[str, float]:
        return {pid: league_points(proj.stats, self.scoring_settings) for pid, proj in self.season_projections.items()}

    def opponents(self) -> dict[str, str | None]:
        return {pid: proj.opponent for pid, proj in self.weekly_projections.items()}

    def roster(self, roster_id: int) -> Roster:
        for item in self.rosters:
            if item.roster_id == roster_id:
                return item
        raise KeyError(f"Roster {roster_id} not in league {self.league.league_id}")

    def user_for_roster(self, roster: Roster) -> User | None:
        for user in self.users:
            if user.user_id == roster.owner_id:
                return user
        return None

    def roster_players(self, roster: Roster) -> list[Player]:
        return [self.players[pid] for pid in roster.players if pid in self.players]


def nfl_state_from_optional(state: NFLState | None, league: League) -> tuple[str, int, str]:
    if state is None:
        return league.season, 1, league.season_type or "regular"
    season = state.league_season or state.season or league.season
    week = state.current_week
    return season, week, state.season_type or "regular"
