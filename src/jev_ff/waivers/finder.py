"""Rank free agents by value over replacement, with an optional Jev overlay."""

from __future__ import annotations

from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import JevResult
from jev_ff.lineup.slots import player_can_fill, starter_slots
from jev_ff.sleeper.models import Player, Roster
from jev_ff.sleeper.schedule import is_on_bye, is_out
from jev_ff.waivers.models import WaiverAdd, WaiverReport

FAAB_LABELS = ["Ignore / $0", "Streaming / cheap", "Solid upgrade", "Must-add"]


def find_waivers(
    *,
    week: int,
    season: str,
    roster: Roster,
    rosters: list[Roster],
    players: dict[str, Player],
    roster_positions: list[str],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    trending: dict[str, int],
    bye_teams: set[str],
    headlines: dict[str, list[str]],
    scoring_settings: dict[str, float],
    advisor: JevAdvisor | None = None,
    limit: int = 10,
) -> WaiverReport:
    owned: set[str] = set()
    for item in rosters:
        owned.update(item.players)
        if item.reserve:
            owned.update(item.reserve)
        if item.taxi:
            owned.update(item.taxi)

    slots = starter_slots(roster_positions)
    my_players = [players[pid] for pid in roster.players if pid in players]
    replacement = _replacement_levels(my_players, slots, week_points, ros_points, bye_teams)

    drop_candidates = _drop_candidates(my_players, week_points, ros_points, roster)
    primary_drop = drop_candidates[0][0] if drop_candidates else None

    ranked: list[WaiverAdd] = []
    for player_id, player in players.items():
        if player_id in owned:
            continue
        if player.status and player.status not in {"Active", "Injured Reserve", None}:
            if player.position not in {"DEF", "K"} and not player.team:
                continue
        if not player.positions or player.position in {"OL", "OT", "OG", "C", "LS", "P"}:
            continue
        if is_out(player) and player.injury_status in {"IR", "PUP", "Suspended"}:
            continue
        week_pts = 0.0 if is_on_bye(player, bye_teams, None) else week_points.get(player_id, 0.0)
        ros_pts = ros_points.get(player_id, 0.0)
        if week_pts <= 0 and ros_pts <= 0 and trending.get(player_id, 0) == 0:
            continue
        vor_week, vor_ros = _vor(player, slots, week_pts, ros_pts, replacement)
        trend = trending.get(player_id, 0)
        score = 0.6 * vor_week + 0.4 * vor_ros + min(trend, 200) / 200.0
        ranked.append(
            WaiverAdd(
                player=player,
                week_points=round(week_pts, 2),
                ros_points=round(ros_pts, 2),
                vor_week=round(vor_week, 2),
                vor_ros=round(vor_ros, 2),
                score=round(score, 4),
                trending_adds=trend,
                drop=primary_drop,
                reason="VOR vs current starters",
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    top = ranked[: max(limit, 1)]

    jev_result: JevResult | None = None
    jev_enabled = bool(advisor and advisor.enabled)
    notes: list[str] = []
    if advisor and advisor.enabled and top:
        jev_result = advisor.evaluate_waivers(
            week=week,
            scoring_settings=scoring_settings,
            adds=[(row.player, row.week_points, row.ros_points) for row in top],
            drops=drop_candidates,
            headlines=headlines,
        )
        if jev_result:
            for row in top:
                worth = jev_result.nouls.get(f"worth_{row.player.player_id}")
                faab = jev_result.scores.get(f"faab_{row.player.player_id}")
                if worth:
                    row.worth_it = worth.noul
                    if worth.noul < 0.4:
                        row.score -= 1.0
                    elif worth.noul > 0.7:
                        row.score += 0.5
                if faab:
                    row.faab_score = faab.score
                    idx = min(3, max(0, int(round(faab.score))))
                    row.faab_label = FAAB_LABELS[idx]
                    row.reason = f"{row.reason}; FAAB: {row.faab_label}"
            choice = jev_result.choices.get("best_drop")
            if choice and choice.choice != "other" and choice.choice in players:
                suggested = players[choice.choice]
                notes.append(f"Jev preferred drop: {suggested.full_name}")
                for row in top:
                    row.drop = suggested
            top.sort(key=lambda item: item.score, reverse=True)

    suggested_drop = top[0].drop if top else primary_drop
    return WaiverReport(
        week=week,
        season=season,
        roster_id=roster.roster_id,
        adds=top,
        jev_enabled=jev_enabled,
        notes=notes,
        suggested_drop=suggested_drop,
    )


def _replacement_levels(
    my_players: list[Player],
    slots: list[str],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    bye_teams: set[str],
) -> dict[str, tuple[float, float]]:
    """Weakest relevant starter-level value at each slot type."""
    levels: dict[str, tuple[float, float]] = {}
    unique_slots = list(dict.fromkeys(slots))
    for slot in unique_slots:
        eligible = [
            p for p in my_players if player_can_fill(p, slot) and not is_on_bye(p, bye_teams, None) and not is_out(p)
        ]
        if not eligible:
            levels[slot] = (0.0, 0.0)
            continue
        eligible.sort(key=lambda p: week_points.get(p.player_id, 0.0), reverse=True)
        count = slots.count(slot)
        # Replacement is the last starter at this slot, or 0 if we can't fill it.
        starter_pool = eligible[: max(count, 1)]
        worst = starter_pool[-1]
        levels[slot] = (
            week_points.get(worst.player_id, 0.0),
            ros_points.get(worst.player_id, 0.0),
        )
    return levels


def _vor(
    player: Player,
    slots: list[str],
    week_pts: float,
    ros_pts: float,
    replacement: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    best_week = -999.0
    best_ros = -999.0
    matched = False
    for slot in dict.fromkeys(slots):
        if not player_can_fill(player, slot):
            continue
        matched = True
        week_rep, ros_rep = replacement.get(slot, (0.0, 0.0))
        best_week = max(best_week, week_pts - week_rep)
        best_ros = max(best_ros, ros_pts - ros_rep)
    if not matched:
        return week_pts, ros_pts
    return best_week, best_ros


def _drop_candidates(
    my_players: list[Player],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    roster: Roster,
) -> list[tuple[Player, float]]:
    starters = set(roster.starters)
    bench = [p for p in my_players if p.player_id not in starters]
    if not bench:
        bench = list(my_players)
    bench.sort(key=lambda p: (ros_points.get(p.player_id, 0.0), week_points.get(p.player_id, 0.0)))
    return [(p, ros_points.get(p.player_id, 0.0)) for p in bench[:8]]
