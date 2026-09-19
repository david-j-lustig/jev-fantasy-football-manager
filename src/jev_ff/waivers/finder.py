"""Rank free agents by value over replacement, with an optional Jev overlay."""

from __future__ import annotations

from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import JevResult
from jev_ff.lineup.slots import player_can_fill, slot_sort_key, starter_slots
from jev_ff.sleeper.models import Player, Roster
from jev_ff.sleeper.schedule import is_on_bye, is_out
from jev_ff.waivers.models import WaiverAdd, WaiverReport

FAAB_LABELS = ["Ignore / $0", "Streaming / cheap", "Solid upgrade", "Must-add"]
NON_FANTASY_POSITIONS = {"OL", "OT", "OG", "C", "LS", "P"}
UNAVAILABLE_STATUSES = {"IR", "PUP", "Suspended"}


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
    owned_ids = _owned_player_ids(rosters)
    slots = starter_slots(roster_positions)
    my_players = [players[player_id] for player_id in roster.players if player_id in players]
    replacement = _replacement_levels(my_players, slots, week_points, ros_points, bye_teams)
    drop_candidates = _drop_candidates(my_players, week_points, ros_points, roster)
    primary_drop = drop_candidates[0][0] if drop_candidates else None

    ranked = _rank_free_agents(
        players=players,
        owned_ids=owned_ids,
        slots=slots,
        week_points=week_points,
        ros_points=ros_points,
        trending=trending,
        bye_teams=bye_teams,
        replacement=replacement,
        primary_drop=primary_drop,
    )
    top = ranked[: max(limit, 1)]
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
            _apply_jev_to_adds(top, jev_result, players, notes)

    return WaiverReport(
        week=week,
        season=season,
        roster_id=roster.roster_id,
        adds=top,
        jev_enabled=bool(advisor and advisor.enabled),
        notes=notes,
        suggested_drop=top[0].drop if top else primary_drop,
    )


def _owned_player_ids(rosters: list[Roster]) -> set[str]:
    owned: set[str] = set()
    for roster in rosters:
        owned.update(roster.players)
        if roster.reserve:
            owned.update(roster.reserve)
        if roster.taxi:
            owned.update(roster.taxi)
    return owned


def _is_waiver_candidate(player: Player) -> bool:
    if player.status and player.status not in {"Active", "Injured Reserve", None}:
        if player.position not in {"DEF", "K"} and not player.team:
            return False
    if not player.positions or player.position in NON_FANTASY_POSITIONS:
        return False
    if is_out(player) and player.injury_status in UNAVAILABLE_STATUSES:
        return False
    return True


def _rank_free_agents(
    *,
    players: dict[str, Player],
    owned_ids: set[str],
    slots: list[str],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    trending: dict[str, int],
    bye_teams: set[str],
    replacement: dict[str, tuple[float, float]],
    primary_drop: Player | None,
) -> list[WaiverAdd]:
    ranked: list[WaiverAdd] = []
    for player_id, player in players.items():
        if player_id in owned_ids or not _is_waiver_candidate(player):
            continue
        week_score = 0.0 if is_on_bye(player, bye_teams, None) else week_points.get(player_id, 0.0)
        ros_score = ros_points.get(player_id, 0.0)
        trend = trending.get(player_id, 0)
        if week_score <= 0 and ros_score <= 0 and trend == 0:
            continue
        vor_week, vor_ros = _value_over_replacement(player, slots, week_score, ros_score, replacement)
        ranked.append(
            WaiverAdd(
                player=player,
                week_points=round(week_score, 2),
                ros_points=round(ros_score, 2),
                vor_week=round(vor_week, 2),
                vor_ros=round(vor_ros, 2),
                score=round(0.6 * vor_week + 0.4 * vor_ros + min(trend, 200) / 200.0, 4),
                trending_adds=trend,
                drop=primary_drop,
                reason="VOR vs current starters",
            )
        )
    ranked.sort(key=lambda add: add.score, reverse=True)
    return ranked


def _apply_jev_to_adds(
    adds: list[WaiverAdd],
    jev_result: JevResult,
    players: dict[str, Player],
    notes: list[str],
) -> None:
    for row in adds:
        worth_it = jev_result.nouls.get(f"worth_{row.player.player_id}")
        faab_answer = jev_result.scores.get(f"faab_{row.player.player_id}")
        if worth_it:
            row.worth_it = worth_it.noul
            if worth_it.noul < 0.4:
                row.score -= 1.0
            elif worth_it.noul > 0.7:
                row.score += 0.5
        if faab_answer:
            index = min(3, max(0, int(round(faab_answer.score))))
            row.faab_score = faab_answer.score
            row.faab_label = FAAB_LABELS[index]
            row.reason = f"{row.reason}; FAAB: {row.faab_label}"
    choice = jev_result.choices.get("best_drop")
    if choice and choice.choice != "other" and choice.choice in players:
        suggested = players[choice.choice]
        notes.append(f"Jev preferred drop: {suggested.full_name}")
        for row in adds:
            row.drop = suggested
    adds.sort(key=lambda add: add.score, reverse=True)


def _replacement_levels(
    my_players: list[Player],
    slots: list[str],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    bye_teams: set[str],
) -> dict[str, tuple[float, float]]:
    assigned = _assigned_starters(my_players, slots, week_points, bye_teams)
    levels: dict[str, tuple[float, float]] = {}
    for slot in dict.fromkeys(slots):
        occupants = assigned.get(slot) or []
        if not occupants:
            levels[slot] = (0.0, 0.0)
            continue
        worst = min(occupants, key=lambda player: week_points.get(player.player_id, 0.0))
        levels[slot] = (
            week_points.get(worst.player_id, 0.0),
            ros_points.get(worst.player_id, 0.0),
        )
    return levels


def _assigned_starters(
    my_players: list[Player],
    slots: list[str],
    week_points: dict[str, float],
    bye_teams: set[str],
) -> dict[str, list[Player]]:
    """Greedy starters in slot-priority order so FLEX replacement is the leftover, not WR1/RB1."""
    available = [player for player in my_players if not is_on_bye(player, bye_teams, None) and not is_out(player)]
    available.sort(key=lambda player: week_points.get(player.player_id, 0.0), reverse=True)
    used_ids: set[str] = set()
    assigned: dict[str, list[Player]] = {slot: [] for slot in dict.fromkeys(slots)}
    for _, slot in sorted(enumerate(slots), key=slot_sort_key):
        pick = next(
            (player for player in available if player.player_id not in used_ids and player_can_fill(player, slot)),
            None,
        )
        if pick is None:
            continue
        used_ids.add(pick.player_id)
        assigned[slot].append(pick)
    return assigned


def _value_over_replacement(
    player: Player,
    slots: list[str],
    week_points: float,
    ros_points: float,
    replacement: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    best_week = -999.0
    best_ros = -999.0
    matched = False
    for slot in dict.fromkeys(slots):
        if not player_can_fill(player, slot):
            continue
        matched = True
        week_replacement, ros_replacement = replacement.get(slot, (0.0, 0.0))
        best_week = max(best_week, week_points - week_replacement)
        best_ros = max(best_ros, ros_points - ros_replacement)
    if not matched:
        return week_points, ros_points
    return best_week, best_ros


def _drop_candidates(
    my_players: list[Player],
    week_points: dict[str, float],
    ros_points: dict[str, float],
    roster: Roster,
) -> list[tuple[Player, float]]:
    starters = set(roster.starters)
    bench = [player for player in my_players if player.player_id not in starters] or list(my_players)
    bench.sort(
        key=lambda player: (
            ros_points.get(player.player_id, 0.0),
            week_points.get(player.player_id, 0.0),
        )
    )
    return [(player, ros_points.get(player.player_id, 0.0)) for player in bench[:8]]
