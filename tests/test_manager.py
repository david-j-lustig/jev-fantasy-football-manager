from tests.factories import make_player, sample_league, sample_roster, sample_user

from jev_ff.context import LeagueContext
from jev_ff.jev.client import NullJevEvaluator
from jev_ff.manager import FantasyManager
from jev_ff.sleeper.models import Projection


def test_recommend_lineup_from_context() -> None:
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
    ctx = LeagueContext(
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
    mgr = FantasyManager("L1", roster_id=1, jev=NullJevEvaluator())
    report = mgr.recommend_lineup(context=ctx)
    names = [row.player.full_name for row in report.starters if row.player]
    assert "R Three" in names
    assert report.projected_total >= report.current_total
    assert report.week == 3
