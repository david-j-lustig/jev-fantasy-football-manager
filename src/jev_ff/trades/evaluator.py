"""Evaluate a user-specified give/get trade using ROS points plus Jev fairness."""

from __future__ import annotations

from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import JevResult
from jev_ff.jev.state import player_card, scoring_summary
from jev_ff.sleeper.models import Player, Roster
from jev_ff.trades.models import TradeReport, TradeSide

FAIRNESS_LABELS = [
    "Bad trade",
    "Slight loss",
    "Even",
    "Slight win",
    "Strong steal",
]


def evaluate_trade(
    *,
    week: int,
    season: str,
    roster: Roster,
    give: list[Player],
    get: list[Player],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    scoring_settings: dict[str, float],
    headlines: dict[str, list[str]],
    opponent_roster: Roster | None = None,
    advisor: JevAdvisor | None = None,
) -> TradeReport:
    give_week = _side_total(give, week_points)
    get_week = _side_total(get, week_points)
    give_ros = _side_total(give, ros_points)
    get_ros = _side_total(get, ros_points)
    ros_delta = round(get_ros - give_ros, 2)
    week_delta = round(get_week - give_week, 2)

    report = TradeReport(
        week=week,
        season=season,
        roster_id=roster.roster_id,
        opponent_roster_id=None if opponent_roster is None else opponent_roster.roster_id,
        give=TradeSide(players=give, week_points=round(give_week, 2), ros_points=round(give_ros, 2)),
        get=TradeSide(players=get, week_points=round(get_week, 2), ros_points=round(get_ros, 2)),
        ros_delta=ros_delta,
        week_delta=week_delta,
        recommendation=_points_recommendation(ros_delta),
        jev_enabled=bool(advisor and advisor.enabled),
    )
    if not advisor or not advisor.enabled:
        report.fairness_label = "Points only"
        return report

    result = advisor.evaluate_trade(
        _trade_state(
            week=week,
            roster=roster,
            give=give,
            get=get,
            week_points=week_points,
            ros_points=ros_points,
            scoring_settings=scoring_settings,
            headlines=headlines,
            ros_delta=ros_delta,
            week_delta=week_delta,
        )
    )
    if result:
        _apply_jev_fairness(report, result)
    return report


def _side_total(players: list[Player], points: dict[str, float]) -> float:
    return sum(points.get(player.player_id, 0.0) for player in players)


def _points_recommendation(ros_delta: float) -> str:
    if ros_delta > 8:
        return "Accept on value — you gain substantial ROS points."
    if ros_delta > 1:
        return "Lean accept on rest-of-season points."
    if ros_delta > -1:
        return "Roughly even on rest-of-season points."
    if ros_delta > -8:
        return "Lean decline on rest-of-season points."
    return "Decline on value — you lose substantial ROS points."


def _trade_state(
    *,
    week: int,
    roster: Roster,
    give: list[Player],
    get: list[Player],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    scoring_settings: dict[str, float],
    headlines: dict[str, list[str]],
    ros_delta: float,
    week_delta: float,
) -> dict:
    return {
        "week": week,
        "scoring": scoring_summary(scoring_settings),
        "your_roster_id": roster.roster_id,
        "give": [_player_trade_card(player, week_points, ros_points, headlines) for player in give],
        "get": [_player_trade_card(player, week_points, ros_points, headlines) for player in get],
        "ros_delta": ros_delta,
        "week_delta": week_delta,
    }


def _player_trade_card(
    player: Player,
    week_points: dict[str, float],
    ros_points: dict[str, float],
    headlines: dict[str, list[str]],
) -> dict:
    return player_card(
        player,
        projected_points=week_points.get(player.player_id, 0.0),
        ros_points=ros_points.get(player.player_id, 0.0),
        headlines=headlines.get(player.player_id, []),
    )


def _apply_jev_fairness(report: TradeReport, result: JevResult) -> None:
    fairness = result.scores.get("fairness")
    if fairness:
        index = min(4, max(0, int(round(fairness.score))))
        report.fairness_score = fairness.score
        report.fairness_label = FAIRNESS_LABELS[index]
        report.notes.append(f"Jev fairness: {report.fairness_label} ({fairness.score:.2f}).")
    accept = result.nouls.get("should_accept")
    opponent = result.nouls.get("opponent_accept")
    if accept:
        report.should_accept = accept.noul
        if accept.noul >= 0.6:
            report.recommendation = "Jev: accept."
        elif accept.noul <= 0.4:
            report.recommendation = "Jev: decline."
    if opponent:
        report.opponent_would_accept = opponent.noul
        if opponent.noul < 0.35:
            report.notes.append("Jev thinks the other manager is unlikely to accept.")
        elif opponent.noul > 0.65:
            report.notes.append("Jev thinks a typical opponent would accept.")
