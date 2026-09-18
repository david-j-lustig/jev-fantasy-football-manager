"""Public facade: load a Sleeper league and recommend lineup / waivers / trades."""

from __future__ import annotations

from collections.abc import Sequence

from jev_ff.config import Settings, load_settings
from jev_ff.context import LeagueContext
from jev_ff.errors import ConfigError, SleeperError
from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import JevEvaluator, NullJevEvaluator, TypeSafeJevEvaluator
from jev_ff.lineup.optimizer import (
    build_player_values,
    current_starter_total,
    fill_ineligible_if_needed,
    optimize_lineup,
    report_from_solution,
)
from jev_ff.lineup.slots import starter_slots
from jev_ff.models import LineupReport, TradeReport, WaiverReport
from jev_ff.names import resolve_players
from jev_ff.providers import (
    InjuryNewsProvider,
    NewsProvider,
    ProjectionsProvider,
    SleeperProjectionsProvider,
)
from jev_ff.sleeper.cache import JsonFileCache
from jev_ff.sleeper.client import SleeperClient
from jev_ff.sleeper.models import Player, Roster
from jev_ff.sleeper.schedule import bye_teams_from_projections, bye_teams_from_schedule
from jev_ff.trades.evaluator import evaluate_trade
from jev_ff.waivers.finder import find_waivers


class FantasyManager:
    def __init__(
        self,
        league_id: str,
        roster_id: int | None = None,
        *,
        username: str | None = None,
        sleeper: SleeperClient | None = None,
        projections: ProjectionsProvider | None = None,
        news: NewsProvider | None = None,
        jev: JevEvaluator | None = None,
        typesafe_api_key: str | None = None,
        model: str = "jev-latest",
        cache: JsonFileCache | None = None,
    ) -> None:
        self.league_id = league_id
        self._roster_id = roster_id
        self.username = username
        self.sleeper = sleeper or SleeperClient(cache=cache)
        self.projections = projections or SleeperProjectionsProvider(self.sleeper)
        self.news = news or InjuryNewsProvider()
        if jev is not None:
            self.jev = jev
        elif typesafe_api_key:
            self.jev = TypeSafeJevEvaluator(api_key=typesafe_api_key, model=model)
        else:
            self.jev = NullJevEvaluator()
        self.advisor = JevAdvisor(self.jev, enabled=not isinstance(self.jev, NullJevEvaluator))
        self.model = model
        self._resolved_roster_id: int | None = None

    @classmethod
    def from_env(
        cls,
        league_id: str | None = None,
        roster_id: int | None = None,
        username: str | None = None,
        *,
        typesafe_api_key: str | None = None,
        model: str | None = None,
    ) -> FantasyManager:
        settings = load_settings(
            league_id=league_id,
            roster_id=roster_id,
            username=username,
            typesafe_api_key=typesafe_api_key,
            model=model,
        )
        return cls.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: object) -> FantasyManager:
        return cls(
            league_id=settings.league_id,
            roster_id=settings.roster_id,
            username=settings.username,
            typesafe_api_key=settings.typesafe_api_key,
            model=settings.model,
            **kwargs,  # type: ignore[arg-type]
        )

    @property
    def jev_enabled(self) -> bool:
        return self.advisor.enabled

    def load_context(self, week: int | None = None) -> LeagueContext:
        league = self.sleeper.get_league(self.league_id)
        state = self.sleeper.get_state()
        season = state.league_season or state.season or league.season
        season_type = state.season_type or league.season_type or "regular"
        resolved_week = int(week or state.current_week)
        rosters = self.sleeper.get_rosters(self.league_id)
        users = self.sleeper.get_users(self.league_id)
        players = self.sleeper.get_players()
        weekly = self.projections.weekly(season, resolved_week, season_type=season_type)
        ros = self.projections.rest_of_season(season, season_type=season_type)
        try:
            trending_raw = self.sleeper.get_trending(limit=50)
            trending = {item.player_id: item.count for item in trending_raw}
        except SleeperError:
            trending = {}
        schedule = self.sleeper.get_schedule(season, season_type=season_type)
        bye_teams = bye_teams_from_schedule(schedule, resolved_week)
        if not bye_teams:
            bye_teams = bye_teams_from_projections(weekly, players)
        headlines: dict[str, list[str]] = {}
        interesting = set()
        for roster in rosters:
            interesting.update(roster.players)
        for pid in list(interesting)[:200]:
            player = players.get(pid)
            if player is None:
                continue
            notes = self.news.headlines(player, week=resolved_week)
            if notes:
                headlines[pid] = notes
        return LeagueContext(
            league=league,
            rosters=rosters,
            users=users,
            players=players,
            week=resolved_week,
            season=season,
            season_type=season_type,
            weekly_projections=weekly,
            season_projections=ros,
            trending=trending,
            bye_teams=bye_teams,
            headlines=headlines,
        )

    def resolve_roster_id(self, context: LeagueContext | None = None) -> int:
        if self._resolved_roster_id is not None:
            return self._resolved_roster_id
        if self._roster_id is not None:
            self._resolved_roster_id = self._roster_id
            return self._roster_id
        ctx = context or self.load_context()
        if not self.username:
            raise ConfigError("Pass roster_id or username so we know which team to manage.")
        user_payload = self.sleeper.get_user(self.username)
        user_id = str(user_payload["user_id"])
        for roster in ctx.rosters:
            if roster.owner_id == user_id:
                self._resolved_roster_id = roster.roster_id
                return roster.roster_id
        raise ConfigError(f"User {self.username} does not own a roster in league {self.league_id}.")

    def recommend_lineup(self, week: int | None = None, context: LeagueContext | None = None) -> LineupReport:
        ctx = context or self.load_context(week)
        roster = ctx.roster(self.resolve_roster_id(ctx))
        slots = starter_slots(ctx.league.roster_positions)
        week_points = ctx.week_points()
        values = build_player_values(
            ctx.roster_players(roster),
            week_points,
            bye_teams=ctx.bye_teams,
            projections_opponents=ctx.opponents(),
        )
        solution = optimize_lineup(slots, values)
        solution = fill_ineligible_if_needed(slots, solution, values)
        notes: list[str] = list(solution.notes)
        jev_notes: list[str] = []
        if self.advisor.enabled:
            adjusted, jev_notes, _ = self.advisor.overlay_lineup(
                week=ctx.week,
                scoring_settings=ctx.scoring_settings,
                solution=solution,
                pool=values,
                headlines=ctx.headlines,
                opponents=ctx.opponents(),
            )
            solution = optimize_lineup(slots, adjusted)
            solution = fill_ineligible_if_needed(slots, solution, adjusted)
            values = adjusted
        solution.notes = notes + jev_notes
        current_total = current_starter_total(roster, values, slots)
        return report_from_solution(
            week=ctx.week,
            season=ctx.season,
            roster_id=roster.roster_id,
            solution=solution,
            current_total=current_total,
            jev_enabled=self.advisor.enabled,
        )

    def find_waivers(
        self,
        week: int | None = None,
        *,
        limit: int = 10,
        context: LeagueContext | None = None,
    ) -> WaiverReport:
        ctx = context or self.load_context(week)
        roster = ctx.roster(self.resolve_roster_id(ctx))
        return find_waivers(
            week=ctx.week,
            season=ctx.season,
            roster=roster,
            rosters=ctx.rosters,
            players=ctx.players,
            roster_positions=ctx.league.roster_positions,
            week_points=ctx.week_points(),
            ros_points=ctx.ros_points(),
            trending=ctx.trending,
            bye_teams=ctx.bye_teams,
            headlines=ctx.headlines,
            scoring_settings=ctx.scoring_settings,
            advisor=self.advisor,
            limit=limit,
        )

    def evaluate_trade(
        self,
        give: Sequence[str],
        get: Sequence[str],
        *,
        week: int | None = None,
        opponent_roster_id: int | None = None,
        context: LeagueContext | None = None,
    ) -> TradeReport:
        ctx = context or self.load_context(week)
        roster = ctx.roster(self.resolve_roster_id(ctx))
        give_players = resolve_players(list(give), ctx.players)
        get_players = resolve_players(list(get), ctx.players)
        opponent = _infer_opponent(ctx.rosters, get_players, opponent_roster_id)
        # Headlines for trade pieces even if they weren't on our roster.
        for player in [*give_players, *get_players]:
            if player.player_id not in ctx.headlines:
                notes = self.news.headlines(player, week=ctx.week)
                if notes:
                    ctx.headlines[player.player_id] = notes
        return evaluate_trade(
            week=ctx.week,
            season=ctx.season,
            roster=roster,
            give=give_players,
            get=get_players,
            week_points=ctx.week_points(),
            ros_points=ctx.ros_points(),
            scoring_settings=ctx.scoring_settings,
            headlines=ctx.headlines,
            opponent_roster=opponent,
            advisor=self.advisor,
        )


def _infer_opponent(
    rosters: list[Roster],
    get_players: list[Player],
    opponent_roster_id: int | None,
) -> Roster | None:
    if opponent_roster_id is not None:
        for roster in rosters:
            if roster.roster_id == opponent_roster_id:
                return roster
        return None
    get_ids = {p.player_id for p in get_players}
    matches = [roster for roster in rosters if get_ids & set(roster.players)]
    if len(matches) == 1:
        return matches[0]
    return None
