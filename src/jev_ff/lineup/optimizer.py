"""Assign roster players to starter slots, maximizing league-scored projections."""

from __future__ import annotations

from dataclasses import dataclass, field

from jev_ff.lineup.models import LineupAssignment, LineupReport
from jev_ff.lineup.slots import player_can_fill, slot_sort_key
from jev_ff.sleeper.models import Player, Roster
from jev_ff.sleeper.schedule import is_on_bye, is_out

CLOSE_CALL_POINTS = 3.0


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


@dataclass
class LineupSolution:
    assignments: list[tuple[str, PlayerValue | None]]
    bench: list[PlayerValue]
    notes: list[str] = field(default_factory=list)

    @property
    def projected_total(self) -> float:
        return round(sum(pv.points for _, pv in self.assignments if pv is not None), 4)


MAX_CANDIDATES_PER_SLOT = 6


def optimize_lineup(
    slots: list[str],
    candidates: list[PlayerValue],
) -> LineupSolution:
    """Assign players to starter slots, maximizing projected points.

    Tries optional PuLP ILP when installed (``pip install jev-fantasy-football-manager[ilp]``),
    otherwise an exact-enough backtracking search on the top candidates per slot.
    """
    pulp_solution = _optimize_pulp(slots, candidates)
    if pulp_solution is not None:
        return pulp_solution
    return _optimize_backtrack(slots, candidates)


def _finish(
    slots: list[str],
    candidates: list[PlayerValue],
    chosen: list[tuple[int, PlayerValue | None]],
) -> LineupSolution:
    by_index = {index: pv for index, pv in chosen}
    assignments = [(slot, by_index.get(i)) for i, slot in enumerate(slots)]
    used = {pv.player_id for _, pv in assignments if pv is not None}
    bench = [pv for pv in candidates if pv.player_id not in used]
    bench.sort(key=lambda pv: pv.points, reverse=True)
    return LineupSolution(assignments=assignments, bench=bench)


def _optimize_backtrack(slots: list[str], candidates: list[PlayerValue]) -> LineupSolution:
    ordered_slots = sorted(enumerate(slots), key=slot_sort_key)
    eligible = [pv for pv in candidates if pv.eligible]
    best: list[tuple[int, PlayerValue | None]] | None = None
    best_score = float("-inf")

    def score_of(chosen: list[tuple[int, PlayerValue | None]]) -> float:
        return sum(pv.points for _, pv in chosen if pv is not None)

    def rec(i: int, remaining: list[PlayerValue], chosen: list[tuple[int, PlayerValue | None]]) -> None:
        nonlocal best, best_score
        if i == len(ordered_slots):
            total = score_of(chosen)
            if total > best_score:
                best_score = total
                best = list(chosen)
            return
        optimistic = score_of(chosen) + sum(max(pv.points, 0.0) for pv in remaining)
        if optimistic < best_score:
            return
        slot_index, slot = ordered_slots[i]
        fits = [pv for pv in remaining if player_can_fill(pv.player, slot)]
        fits.sort(key=lambda pv: pv.points, reverse=True)
        options: list[PlayerValue | None] = fits[:MAX_CANDIDATES_PER_SLOT] or [None]
        for pick in options:
            nxt = remaining if pick is None else [pv for pv in remaining if pv.player_id != pick.player_id]
            chosen.append((slot_index, pick))
            rec(i + 1, nxt, chosen)
            chosen.pop()

    rec(0, eligible, [])
    if best is None:
        return LineupSolution(
            assignments=[(slot, None) for slot in slots],
            bench=list(candidates),
            notes=["No eligible players."],
        )
    return _finish(slots, candidates, best)


def _optimize_pulp(slots: list[str], candidates: list[PlayerValue]) -> LineupSolution | None:
    try:
        import pulp
    except ImportError:
        return None
    eligible = [pv for pv in candidates if pv.eligible]
    if not eligible:
        return None
    by_id = {pv.player_id: pv for pv in eligible}
    problem = pulp.LpProblem("lineup", pulp.LpMaximize)
    variables: dict[tuple[int, str], object] = {}
    for i, slot in enumerate(slots):
        for pv in eligible:
            if player_can_fill(pv.player, slot):
                variables[i, pv.player_id] = pulp.LpVariable(
                    f"s{i}_{pv.player_id}", lowBound=0, upBound=1, cat="Binary"
                )
    if not variables:
        return None
    problem += pulp.lpSum(variables[i, pid] * by_id[pid].points for i, pid in variables)
    for i, slot in enumerate(slots):
        slot_vars = [variables[key] for key in variables if key[0] == i]
        if slot_vars:
            problem += pulp.lpSum(slot_vars) <= 1, f"slot_{i}"
    for pid in by_id:
        player_vars = [variables[key] for key in variables if key[1] == pid]
        if player_vars:
            problem += pulp.lpSum(player_vars) <= 1, f"player_{pid}"
    try:
        status = problem.solve(pulp.PULP_CBC_CMD(msg=False))
    except Exception:
        return None
    if pulp.LpStatus[status] != "Optimal":
        return None
    chosen: list[tuple[int, PlayerValue | None]] = []
    for i, _slot in enumerate(slots):
        pick: PlayerValue | None = None
        for pid, pv in by_id.items():
            var = variables.get((i, pid))
            if var is not None and pulp.value(var) and pulp.value(var) > 0.5:
                pick = pv
                break
        chosen.append((i, pick))
    return _finish(slots, candidates, chosen)


def build_player_values(
    roster_players: list[Player],
    points: dict[str, float],
    *,
    bye_teams: set[str],
    projections_opponents: dict[str, str | None] | None = None,
) -> list[PlayerValue]:
    values: list[PlayerValue] = []
    for player in roster_players:
        opponent = None
        if projections_opponents:
            opponent = projections_opponents.get(player.player_id)
        on_bye = is_on_bye(player, bye_teams, None) or (opponent or "").upper() == "BYE"
        out = is_out(player)
        pts = 0.0 if on_bye else float(points.get(player.player_id, 0.0))
        if on_bye:
            eligible = False
            reason = "Bye week"
        elif out:
            eligible = False
            reason = f"Out ({player.injury_status})"
            pts = 0.0
        else:
            eligible = True
            reason = ""
        values.append(
            PlayerValue(
                player=player,
                points=pts,
                on_bye=on_bye,
                out=out,
                reason=reason,
                eligible=eligible,
            )
        )
    return values


def fill_ineligible_if_needed(slots: list[str], solution: LineupSolution, pool: list[PlayerValue]) -> LineupSolution:
    """If a starter slot is empty, allow an Out player as a last resort. Never start a bye."""
    used = {pv.player_id for _, pv in solution.assignments if pv is not None}
    notes = list(solution.notes)
    assignments = list(solution.assignments)
    for i, (slot, current) in enumerate(assignments):
        if current is not None:
            continue
        backups = [pv for pv in pool if pv.player_id not in used and not pv.on_bye and player_can_fill(pv.player, slot)]
        backups.sort(key=lambda pv: pv.points, reverse=True)
        if not backups:
            notes.append(f"Empty {slot}: no eligible player.")
            continue
        pick = backups[0]
        pick.reason = pick.reason or "Last resort (injury)"
        pick.needs_review = True
        assignments[i] = (slot, pick)
        used.add(pick.player_id)
        notes.append(f"Started {pick.player.full_name} in {slot} as a last resort.")
    used = {pv.player_id for _, pv in assignments if pv is not None}
    bench = [pv for pv in pool if pv.player_id not in used]
    bench.sort(key=lambda pv: pv.points, reverse=True)
    return LineupSolution(assignments=assignments, bench=bench, notes=notes)


def current_starter_total(roster: Roster, values: list[PlayerValue], slots: list[str]) -> float:
    by_id = {pv.player_id: pv for pv in values}
    total = 0.0
    for i, player_id in enumerate(roster.starters):
        if i >= len(slots):
            break
        pv = by_id.get(player_id)
        if pv is not None:
            total += pv.points
    return round(total, 4)


def close_calls(solution: LineupSolution, pool: list[PlayerValue], margin: float = CLOSE_CALL_POINTS) -> list[dict]:
    used = {pv.player_id for _, pv in solution.assignments if pv is not None}
    calls: list[dict] = []
    for slot, starter in solution.assignments:
        if starter is None:
            continue
        sitters = [
            pv
            for pv in pool
            if pv.player_id not in used
            and pv.eligible
            and player_can_fill(pv.player, slot)
            and starter.points - pv.points <= margin
        ]
        if sitters:
            calls.append({"slot": slot, "starter": starter, "sitters": sitters})
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
    starters = [
        LineupAssignment(
            slot=slot,
            player=None if pv is None else pv.player,
            projected_points=0.0 if pv is None else pv.points,
            reason="" if pv is None else pv.reason,
            needs_review=False if pv is None else pv.needs_review,
        )
        for slot, pv in solution.assignments
    ]
    bench = [
        LineupAssignment(
            slot="BN",
            player=pv.player,
            projected_points=pv.points,
            reason=pv.reason,
            needs_review=pv.needs_review,
        )
        for pv in solution.bench
    ]
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
