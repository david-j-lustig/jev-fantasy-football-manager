from tests.factories import make_player, sample_league

from jev_ff.lineup.optimizer import (
    PlayerValue,
    build_player_values,
    optimize_lineup,
)
from jev_ff.lineup.slots import starter_slots


def _pv(player_id: str, name: str, position: str, points: float, **kwargs) -> PlayerValue:
    player = make_player(player_id, name, position, **kwargs)
    return PlayerValue(player=player, points=points, eligible=True)


def _ids(solution) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    counts: dict[str, int] = {}
    for slot, pv in solution.assignments:
        n = counts.get(slot, 0)
        counts[slot] = n + 1
        key = slot if n == 0 else f"{slot}{n + 1}"
        out[key] = None if pv is None else pv.player.full_name
    return out


def test_starter_slots_drop_bench() -> None:
    league = sample_league()
    assert starter_slots(league.roster_positions) == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"]


def test_flex_gets_highest_remaining_skill_player() -> None:
    slots = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"]
    pool = [
        _pv("1", "Q Star", "QB", 20),
        _pv("2", "R One", "RB", 18),
        _pv("3", "R Two", "RB", 15),
        _pv("4", "R Three", "RB", 14),
        _pv("5", "W One", "WR", 16),
        _pv("6", "W Two", "WR", 12),
        _pv("7", "T One", "TE", 10),
        _pv("8", "W Three", "WR", 9),
    ]
    solution = optimize_lineup(slots, pool)
    names = [pv.player.full_name for _, pv in solution.assignments if pv]
    assert "R Three" in names  # 14-pt RB should take FLEX over 12-pt WR
    assert "W Two" in names
    assert solution.projected_total == 20 + 18 + 15 + 16 + 12 + 10 + 14


def test_superflex_starts_second_qb() -> None:
    slots = ["QB", "RB", "WR", "SUPER_FLEX"]
    pool = [
        _pv("1", "Q One", "QB", 22),
        _pv("2", "Q Two", "QB", 18),
        _pv("3", "R One", "RB", 16),
        _pv("4", "W One", "WR", 15),
        _pv("5", "R Two", "RB", 10),
    ]
    solution = optimize_lineup(slots, pool)
    names = [pv.player.full_name for _, pv in solution.assignments if pv]
    assert "Q One" in names and "Q Two" in names
    assert solution.projected_total == 22 + 16 + 15 + 18


def test_bye_and_out_are_ineligible() -> None:
    qb = make_player("1", "Q Star", "QB")
    rb_bye = make_player("2", "Bye Back", "RB", team="CHI")
    rb_out = make_player("3", "Hurt Back", "RB", injury_status="Out")
    rb_ok = make_player("4", "Ok Back", "RB")
    wr = make_player("5", "W One", "WR")
    values = build_player_values(
        [qb, rb_bye, rb_out, rb_ok, wr],
        {"1": 20, "2": 30, "3": 25, "4": 12, "5": 11},
        bye_teams={"CHI"},
    )
    by_id = {pv.player_id: pv for pv in values}
    assert not by_id["2"].eligible
    assert not by_id["3"].eligible
    assert by_id["2"].points == 0
    solution = optimize_lineup(["QB", "RB", "WR"], values)
    names = [pv.player.full_name for _, pv in solution.assignments if pv]
    assert names == ["Q Star", "Ok Back", "W One"]
