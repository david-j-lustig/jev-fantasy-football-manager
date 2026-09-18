from jev_ff.context import LeagueContext
from jev_ff.jev.client import NullJevEvaluator
from jev_ff.lineup.optimizer import build_player_values, optimize_lineup
from jev_ff.manager import FantasyManager
from jev_ff.sleeper.models import Projection
from tests.factories import make_player, make_player_value, sample_league, sample_roster, sample_user


def _starter_names(solution) -> list[str]:
    return [value.player.full_name for _, value in solution.assignments if value]


def test_flex_starts_highest_remaining_skill_player() -> None:
    slots = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"]
    pool = [
        make_player_value("1", "Q Star", "QB", 20),
        make_player_value("2", "R One", "RB", 18),
        make_player_value("3", "R Two", "RB", 15),
        make_player_value("4", "R Three", "RB", 14),
        make_player_value("5", "W One", "WR", 16),
        make_player_value("6", "W Two", "WR", 12),
        make_player_value("7", "T One", "TE", 10),
        make_player_value("8", "W Three", "WR", 9),
    ]
    solution = optimize_lineup(slots, pool)
    names = _starter_names(solution)
    assert "R Three" in names
    assert "W Two" in names
    assert solution.projected_total == 20 + 18 + 15 + 16 + 12 + 10 + 14


def test_superflex_starts_second_quarterback() -> None:
    slots = ["QB", "RB", "WR", "SUPER_FLEX"]
    pool = [
        make_player_value("1", "Q One", "QB", 22),
        make_player_value("2", "Q Two", "QB", 18),
        make_player_value("3", "R One", "RB", 16),
        make_player_value("4", "W One", "WR", 15),
        make_player_value("5", "R Two", "RB", 10),
    ]
    solution = optimize_lineup(slots, pool)
    names = _starter_names(solution)
    assert "Q One" in names and "Q Two" in names
    assert solution.projected_total == 22 + 16 + 15 + 18


def test_bye_and_out_players_are_not_started() -> None:
    quarterback = make_player("1", "Q Star", "QB")
    bye_back = make_player("2", "Bye Back", "RB", team="CHI")
    injured_back = make_player("3", "Hurt Back", "RB", injury_status="Out")
    healthy_back = make_player("4", "Ok Back", "RB")
    receiver = make_player("5", "W One", "WR")
    values = build_player_values(
        [quarterback, bye_back, injured_back, healthy_back, receiver],
        {"1": 20, "2": 30, "3": 25, "4": 12, "5": 11},
        bye_teams={"CHI"},
    )
    values_by_id = {value.player_id: value for value in values}
    assert not values_by_id["2"].eligible
    assert not values_by_id["3"].eligible
    assert values_by_id["2"].points == 0
    solution = optimize_lineup(["QB", "RB", "WR"], values)
    assert _starter_names(solution) == ["Q Star", "Ok Back", "W One"]


def test_recommend_lineup_uses_league_scoring() -> None:
    players = {
        "qb": make_player("qb", "Q Star", "QB"),
        "rb1": make_player("rb1", "R One", "RB"),
        "rb2": make_player("rb2", "R Two", "RB"),
        "wr1": make_player("wr1", "W One", "WR"),
        "wr2": make_player("wr2", "W Two", "WR"),
        "te": make_player("te", "T One", "TE"),
        "flex": make_player("flex", "R Three", "RB"),
    }
    roster = sample_roster(
        1,
        players=list(players),
        starters=["qb", "rb1", "rb2", "wr1", "wr2", "te"],
    )
    context = LeagueContext(
        league=sample_league(),
        rosters=[roster],
        users=[sample_user()],
        players=players,
        week=3,
        season="2025",
        season_type="regular",
        weekly_projections={
            "qb": Projection(player_id="qb", stats={"pass_yd": 250, "pass_td": 2}),
            "rb1": Projection(player_id="rb1", stats={"rush_yd": 80, "rush_td": 1, "rec": 2, "rec_yd": 10}),
            "rb2": Projection(player_id="rb2", stats={"rush_yd": 40, "rec": 3, "rec_yd": 20}),
            "wr1": Projection(player_id="wr1", stats={"rec": 6, "rec_yd": 90, "rec_td": 1}),
            "wr2": Projection(player_id="wr2", stats={"rec": 4, "rec_yd": 50}),
            "te": Projection(player_id="te", stats={"rec": 4, "rec_yd": 40}),
            "flex": Projection(player_id="flex", stats={"rush_yd": 70, "rush_td": 1}),
        },
    )
    manager = FantasyManager("L1", roster_id=1, jev=NullJevEvaluator())
    report = manager.recommend_lineup(context=context)
    names = [row.player.full_name for row in report.starters if row.player]
    assert "R Three" in names
    assert report.projected_total >= report.current_total
    assert report.week == 3
