"""Public facade: load a Sleeper league and recommend lineup / waivers / trades."""

from __future__ import annotations

from collections.abc import Sequence

from jev_ff.config import Settings, load_settings
from jev_ff.context import LeagueContext
from jev_ff.errors import ConfigError, SleeperError
from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import JevEvaluator, NullJevEvaluator, TypeSafeJevEvaluator
from jev_ff.lineup.optimizer import (
    LineupSolution,
    PlayerValue,
    build_player_values,
    current_starter_total,
    fill_empty_slots,
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
from jev_ff.sleeper.models import Player, Projection, Roster
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
        self.jev = _build_jev_evaluator(jev, typesafe_api_key, model)
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
        rest_of_season = self.projections.rest_of_season(season, season_type=season_type)
        return LeagueContext(
            league=league,
            rosters=rosters,
            users=users,
            players=players,
            week=resolved_week,
            season=season,
            season_type=season_type,
            weekly_projections=weekly,
            season_projections=rest_of_season,
            trending=self._trending_adds(),
            bye_teams=self._bye_teams(season, season_type, resolved_week, weekly, players),
            headlines=self._headlines_for_rosters(rosters, players, resolved_week),
        )

    def resolve_roster_id(self, context: LeagueContext | None = None) -> int:
        if self._resolved_roster_id is not None:
            return self._resolved_roster_id
        if self._roster_id is not None:
            self._resolved_roster_id = self._roster_id
            return self._roster_id
        league_context = context or self.load_context()
        if not self.username:
            raise ConfigError("Pass roster_id or username so we know which team to manage.")
        user_id = str(self.sleeper.get_user(self.username)["user_id"])
        for roster in league_context.rosters:
            if roster.owner_id == user_id:
                self._resolved_roster_id = roster.roster_id
                return roster.roster_id
        raise ConfigError(f"User {self.username} does not own a roster in league {self.league_id}.")

    def recommend_lineup(self, week: int | None = None, context: LeagueContext | None = None) -> LineupReport:
        league_context = context or self.load_context(week)
        roster = league_context.roster(self.resolve_roster_id(league_context))
        slots = starter_slots(league_context.league.roster_positions)
        values = build_player_values(
            league_context.roster_players(roster),
            league_context.week_points(),
            bye_teams=league_context.bye_teams,
            projections_opponents=league_context.opponents(),
        )
        solution = _solve_lineup(slots, values)
        notes = list(solution.notes)
        if self.advisor.enabled:
            values, jev_notes = self._overlay_lineup(league_context, solution, values)
            solution = _solve_lineup(slots, values)
            notes.extend(jev_notes)
        solution.notes = notes + solution.notes
        return report_from_solution(
            week=league_context.week,
            season=league_context.season,
            roster_id=roster.roster_id,
            solution=solution,
            current_total=current_starter_total(roster, values, slots),
            jev_enabled=self.advisor.enabled,
        )

    def find_waivers(
        self,
        week: int | None = None,
        *,
        limit: int = 10,
        context: LeagueContext | None = None,
    ) -> WaiverReport:
        league_context = context or self.load_context(week)
        roster = league_context.roster(self.resolve_roster_id(league_context))
        return find_waivers(
            week=league_context.week,
            season=league_context.season,
            roster=roster,
            rosters=league_context.rosters,
            players=league_context.players,
            roster_positions=league_context.league.roster_positions,
            week_points=league_context.week_points(),
            ros_points=league_context.ros_points(),
            trending=league_context.trending,
            bye_teams=league_context.bye_teams,
            headlines=league_context.headlines,
            scoring_settings=league_context.scoring_settings,
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
        league_context = context or self.load_context(week)
        roster = league_context.roster(self.resolve_roster_id(league_context))
        give_players = resolve_players(list(give), league_context.players)
        get_players = resolve_players(list(get), league_context.players)
        self._ensure_trade_headlines(league_context, [*give_players, *get_players])
        return evaluate_trade(
            week=league_context.week,
            season=league_context.season,
            roster=roster,
            give=give_players,
            get=get_players,
            week_points=league_context.week_points(),
            ros_points=league_context.ros_points(),
            scoring_settings=league_context.scoring_settings,
            headlines=league_context.headlines,
            opponent_roster=_opponent_roster(league_context.rosters, get_players, opponent_roster_id),
            advisor=self.advisor,
        )

    def _overlay_lineup(
        self,
        league_context: LeagueContext,
        solution: LineupSolution,
        values: list[PlayerValue],
    ) -> tuple[list[PlayerValue], list[str]]:
        adjusted, notes, _result = self.advisor.overlay_lineup(
            week=league_context.week,
            scoring_settings=league_context.scoring_settings,
            solution=solution,
            pool=values,
            headlines=league_context.headlines,
            opponents=league_context.opponents(),
        )
        return adjusted, notes

    def _trending_adds(self) -> dict[str, int]:
        try:
            return {item.player_id: item.count for item in self.sleeper.get_trending(limit=50)}
        except SleeperError:
            return {}

    def _bye_teams(
        self,
        season: str,
        season_type: str,
        week: int,
        weekly_projections: dict[str, Projection],
        players: dict[str, Player],
    ) -> set[str]:
        schedule = self.sleeper.get_schedule(season, season_type=season_type)
        bye_teams = bye_teams_from_schedule(schedule, week)
        if bye_teams:
            return bye_teams
        return bye_teams_from_projections(weekly_projections, players)

    def _headlines_for_rosters(
        self,
        rosters: list[Roster],
        players: dict[str, Player],
        week: int,
    ) -> dict[str, list[str]]:
        headlines: dict[str, list[str]] = {}
        rostered_ids = {player_id for roster in rosters for player_id in roster.players}
        for player_id in list(rostered_ids)[:200]:
            player = players.get(player_id)
            if player is None:
                continue
            notes = self.news.headlines(player, week=week)
            if notes:
                headlines[player_id] = notes
        return headlines

    def _ensure_trade_headlines(self, league_context: LeagueContext, players: list[Player]) -> None:
        for player in players:
            if player.player_id in league_context.headlines:
                continue
            notes = self.news.headlines(player, week=league_context.week)
            if notes:
                league_context.headlines[player.player_id] = notes


def _build_jev_evaluator(
    jev: JevEvaluator | None,
    typesafe_api_key: str | None,
    model: str,
) -> JevEvaluator:
    if jev is not None:
        return jev
    if typesafe_api_key:
        return TypeSafeJevEvaluator(api_key=typesafe_api_key, model=model)
    return NullJevEvaluator()


def _solve_lineup(slots: list[str], values: list[PlayerValue]) -> LineupSolution:
    return fill_empty_slots(slots, optimize_lineup(slots, values), values)


def _opponent_roster(
    rosters: list[Roster],
    get_players: list[Player],
    opponent_roster_id: int | None,
) -> Roster | None:
    if opponent_roster_id is not None:
        return next((roster for roster in rosters if roster.roster_id == opponent_roster_id), None)
    incoming_ids = {player.player_id for player in get_players}
    matches = [roster for roster in rosters if incoming_ids & set(roster.players)]
    if len(matches) == 1:
        return matches[0]
    return None
