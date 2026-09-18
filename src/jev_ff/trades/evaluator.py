"""Evaluate a user-specified give/get trade using ROS points plus Jev fairness."""

from __future__ import annotations

from jev_ff.jev.advisor import JevAdvisor
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
    give_week = sum(week_points.get(p.player_id, 0.0) for p in give)
    get_week = sum(week_points.get(p.player_id, 0.0) for p in get)
    give_ros = sum(ros_points.get(p.player_id, 0.0) for p in give)
    get_ros = sum(ros_points.get(p.player_id, 0.0) for p in get)
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
        jev_enabled=bool(advisor and advisor.enabled),
    )

    if ros_delta > 8:
        report.recommendation = "Accept on value — you gain substantial ROS points."
    elif ros_delta > 1:
        report.recommendation = "Lean accept on rest-of-season points."
    elif ros_delta > -1:
        report.recommendation = "Roughly even on rest-of-season points."
    elif ros_delta > -8:
        report.recommendation = "Lean decline on rest-of-season points."
    else:
        report.recommendation = "Decline on value — you lose substantial ROS points."

    if not advisor or not advisor.enabled:
        report.fairness_label = "Points only"
        return report

    state = {
        "week": week,
        "scoring": scoring_summary(scoring_settings),
        "your_roster_id": roster.roster_id,
        "give": [
            player_card(
                p,
                projected_points=week_points.get(p.player_id, 0.0),
                ros_points=ros_points.get(p.player_id, 0.0),
                headlines=headlines.get(p.player_id, []),
            )
            for p in give
        ],
        "get": [
            player_card(
                p,
                projected_points=week_points.get(p.player_id, 0.0),
                ros_points=ros_points.get(p.player_id, 0.0),
                headlines=headlines.get(p.player_id, []),
            )
            for p in get
        ],
        "ros_delta": ros_delta,
        "week_delta": week_delta,
    }
    result = advisor.evaluate_trade(state)
    if not result:
        return report
    fairness = result.scores.get("fairness")
    if fairness:
        report.fairness_score = fairness.score
        idx = min(4, max(0, int(round(fairness.score))))
        report.fairness_label = FAIRNESS_LABELS[idx]
        report.notes.append(f"Jev fairness: {report.fairness_label} ({fairness.score:.2f}).")
    accept = result.nouls.get("should_accept")
    opp = result.nouls.get("opponent_accept")
    if accept:
        report.should_accept = accept.noul
    if opp:
        report.opponent_would_accept = opp.noul
    if accept and accept.noul >= 0.6:
        report.recommendation = "Jev: accept."
    elif accept and accept.noul <= 0.4:
        report.recommendation = "Jev: decline."
    if opp and opp.noul < 0.35:
        report.notes.append("Jev thinks the other manager is unlikely to accept.")
    elif opp and opp.noul > 0.65:
        report.notes.append("Jev thinks a typical opponent would accept.")
    return report
