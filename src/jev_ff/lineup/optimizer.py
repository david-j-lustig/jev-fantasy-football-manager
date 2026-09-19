"""Assign roster players to starter slots, maximizing league-scored projections."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from jev_ff.lineup.models import LineupAssignment, LineupReport
from jev_ff.lineup.slots import player_can_fill, slot_sort_key
from jev_ff.sleeper.models import Player, Roster
from jev_ff.sleeper.schedule import is_on_bye, is_out

CLOSE_CALL_POINTS = 3.0
MAX_CANDIDATES_PER_SLOT = 6


@dataclass
class PlayerValue:
    player: Player
    points: float
    on_bye: bool = False
    out: bool = False
    reason: str = ""
    needs_review: bool = False
    eligible: bool = True

    @property
    def player_id(self) -> str:
        return self.player.player_id

    def copy(self, **changes: object) -> PlayerValue:
        return replace(self, **changes)


@dataclass
class LineupSolution:
    assignments: list[tuple[str, PlayerValue | None]]
    bench: list[PlayerValue]
    notes: list[str] = field(default_factory=list)

    @property
    def projected_total(self) -> float:
        return round(sum(value.points for _, value in self.assignments if value is not None), 4)

    def started_ids(self) -> set[str]:
        return {value.player_id for _, value in self.assignments if value is not None}


@dataclass
class CloseCall:
    slot: str
    starter: PlayerValue
    sitters: list[PlayerValue]


def optimize_lineup(slots: list[str], candidates: list[PlayerValue]) -> LineupSolution:
    """Assign players to starter slots, maximizing projected points."""
    return _search_assignments(slots, candidates)


def build_player_values(
    roster_players: list[Player],
    points: dict[str, float],
    *,
    bye_teams: set[str],
    projections_opponents: dict[str, str | None] | None = None,
) -> list[PlayerValue]:
    values: list[PlayerValue] = []
    for player in roster_players:
        opponent = None if projections_opponents is None else projections_opponents.get(player.player_id)
        on_bye = is_on_bye(player, bye_teams, None) or (opponent or "").upper() == "BYE"
        out = is_out(player)
        if on_bye:
            values.append(
                PlayerValue(player=player, points=0.0, on_bye=True, out=out, reason="Bye week", eligible=False)
            )
        elif out:
            values.append(
                PlayerValue(
                    player=player,
                    points=0.0,
                    on_bye=False,
                    out=True,
                    reason=f"Out ({player.injury_status})",
                    eligible=False,
                )
            )
        else:
            values.append(
                PlayerValue(
                    player=player,
                    points=float(points.get(player.player_id, 0.0)),
                    eligible=True,
                )
            )
    return values


def fill_empty_slots(slots: list[str], solution: LineupSolution, pool: list[PlayerValue]) -> LineupSolution:
    """Fill empty starter slots with an injured player as a last resort. Never start a bye."""
    used_ids = solution.started_ids()
    notes = list(solution.notes)
    assignments = list(solution.assignments)
    for index, (slot, current) in enumerate(assignments):
        if current is not None:
            continue
        backup = _last_resort_for_slot(slot, pool, used_ids)
        if backup is None:
            notes.append(f"Empty {slot}: no eligible player.")
            continue
        backup.reason = backup.reason or "Last resort (injury)"
        backup.needs_review = True
        assignments[index] = (slot, backup)
        used_ids.add(backup.player_id)
        notes.append(f"Started {backup.player.full_name} in {slot} as a last resort.")
    return LineupSolution(assignments=assignments, bench=_unused_players(pool, used_ids), notes=notes)


def current_starter_total(roster: Roster, values: list[PlayerValue], slots: list[str]) -> float:
    values_by_id = {value.player_id: value for value in values}
    total = 0.0
    for index, player_id in enumerate(roster.starters):
        if index >= len(slots):
            break
        value = values_by_id.get(player_id)
        if value is not None:
            total += value.points
    return round(total, 4)


def find_close_calls(
    solution: LineupSolution,
    pool: list[PlayerValue],
    margin: float = CLOSE_CALL_POINTS,
) -> list[CloseCall]:
    started_ids = solution.started_ids()
    calls: list[CloseCall] = []
    for slot, starter in solution.assignments:
        if starter is None:
            continue
        sitters = [
            candidate
            for candidate in pool
            if candidate.player_id not in started_ids
            and candidate.eligible
            and player_can_fill(candidate.player, slot)
            and starter.points - candidate.points <= margin
        ]
        if sitters:
            calls.append(CloseCall(slot=slot, starter=starter, sitters=sitters))
    return calls


def report_from_solution(
    *,
    week: int,
    season: str,
    roster_id: int,
    solution: LineupSolution,
    current_total: float,
    jev_enabled: bool = False,
) -> LineupReport:
    starters = [_assignment(slot, value) for slot, value in solution.assignments]
    bench = [_assignment("BN", value) for value in solution.bench]
    return LineupReport(
        week=week,
        season=season,
        roster_id=roster_id,
        starters=starters,
        bench=bench,
        projected_total=solution.projected_total,
        current_total=current_total,
        jev_enabled=jev_enabled,
        notes=solution.notes,
    )


def _assignment(slot: str, value: PlayerValue | None) -> LineupAssignment:
    if value is None:
        return LineupAssignment(slot=slot)
    return LineupAssignment(
        slot=slot,
        player=value.player,
        projected_points=value.points,
        reason=value.reason,
        needs_review=value.needs_review,
    )


def _last_resort_for_slot(slot: str, pool: list[PlayerValue], used_ids: set[str]) -> PlayerValue | None:
    backups = [
        candidate
        for candidate in pool
        if candidate.player_id not in used_ids and not candidate.on_bye and player_can_fill(candidate.player, slot)
    ]
    backups.sort(key=lambda candidate: candidate.points, reverse=True)
    return backups[0] if backups else None


def _solution_from_choices(
    slots: list[str],
    candidates: list[PlayerValue],
    chosen: list[tuple[int, PlayerValue | None]],
) -> LineupSolution:
    by_index = {index: value for index, value in chosen}
    assignments = [(slot, by_index.get(index)) for index, slot in enumerate(slots)]
    started_ids = {value.player_id for _, value in assignments if value is not None}
    return LineupSolution(assignments=assignments, bench=_unused_players(candidates, started_ids))


def _unused_players(candidates: list[PlayerValue], started_ids: set[str]) -> list[PlayerValue]:
    bench = [candidate for candidate in candidates if candidate.player_id not in started_ids]
    bench.sort(key=lambda candidate: candidate.points, reverse=True)
    return bench


def _search_assignments(slots: list[str], candidates: list[PlayerValue]) -> LineupSolution:
    ordered_slots = sorted(enumerate(slots), key=slot_sort_key)
    eligible = [candidate for candidate in candidates if candidate.eligible]
    best_choice: list[tuple[int, PlayerValue | None]] | None = None
    best_score = float("-inf")

    def score_of(chosen: list[tuple[int, PlayerValue | None]]) -> float:
        return sum(value.points for _, value in chosen if value is not None)

    def search(slot_offset: int, remaining: list[PlayerValue], chosen: list[tuple[int, PlayerValue | None]]) -> None:
        nonlocal best_choice, best_score
        if slot_offset == len(ordered_slots):
            total = score_of(chosen)
            if total > best_score:
                best_score = total
                best_choice = list(chosen)
            return
        optimistic = score_of(chosen) + sum(max(candidate.points, 0.0) for candidate in remaining)
        if optimistic < best_score:
            return
        slot_index, slot = ordered_slots[slot_offset]
        fits = [candidate for candidate in remaining if player_can_fill(candidate.player, slot)]
        fits.sort(key=lambda candidate: candidate.points, reverse=True)
        options: list[PlayerValue | None] = fits[:MAX_CANDIDATES_PER_SLOT] or [None]
        for pick in options:
            if pick is None:
                next_remaining = remaining
            else:
                next_remaining = [candidate for candidate in remaining if candidate.player_id != pick.player_id]
            chosen.append((slot_index, pick))
            search(slot_offset + 1, next_remaining, chosen)
            chosen.pop()

    search(0, eligible, [])
    if best_choice is None:
        return LineupSolution(
            assignments=[(slot, None) for slot in slots],
            bench=list(candidates),
            notes=["No eligible players."],
        )
    return _solution_from_choices(slots, candidates, best_choice)
