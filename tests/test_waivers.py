from jev_ff.waivers.finder import find_waivers
from tests.factories import make_player, sample_league, sample_roster


def test_ranks_free_agents_by_value_over_replacement() -> None:
    league = sample_league()
    mine = [
        make_player("qb", "Q Star", "QB"),
        make_player("rb1", "R One", "RB"),
        make_player("rb2", "R Two", "RB"),
        make_player("wr1", "W One", "WR"),
        make_player("wr2", "W Two", "WR"),
        make_player("te", "T One", "TE"),
        make_player("bn", "Bench Dust", "WR"),
    ]
    free_agent = make_player("fa", "Breakout Back", "RB")
    already_owned = make_player("ot", "Other Guy", "RB")
    players = {player.player_id: player for player in [*mine, free_agent, already_owned]}
    roster = sample_roster(
        1,
        players=[player.player_id for player in mine],
        starters=["qb", "rb1", "rb2", "wr1", "wr2", "te"],
    )
    other_roster = sample_roster(2, players=["ot"])
    week_points = {
        "qb": 20,
        "rb1": 15,
        "rb2": 8,
        "wr1": 14,
        "wr2": 12,
        "te": 9,
        "bn": 3,
        "fa": 16,
        "ot": 11,
    }
    ros_points = {player_id: points * 10 for player_id, points in week_points.items()}
    report = find_waivers(
        week=3,
        season="2025",
        roster=roster,
        rosters=[roster, other_roster],
        players=players,
        roster_positions=league.roster_positions,
        week_points=week_points,
        ros_points=ros_points,
        trending={"fa": 80},
        bye_teams=set(),
        headlines={},
        scoring_settings=league.scoring_settings,
        limit=5,
    )
    assert report.adds[0].player.player_id == "fa"
    assert report.adds[0].vor_week > 0
    assert report.suggested_drop is not None
    assert report.suggested_drop.player_id == "bn"
    add_ids = {row.player.player_id for row in report.adds}
    assert "ot" not in add_ids


def test_flex_streamer_beats_current_flex_not_wr1() -> None:
    league = sample_league()
    mine = [
        make_player("qb", "Q Star", "QB"),
        make_player("rb1", "R One", "RB"),
        make_player("rb2", "R Two", "RB"),
        make_player("wr1", "W One", "WR"),
        make_player("wr2", "W Two", "WR"),
        make_player("te", "T One", "TE"),
        make_player("flex", "Flex Back", "RB"),
    ]
    streamer = make_player("fa", "Stream Catch", "WR")
    players = {player.player_id: player for player in [*mine, streamer]}
    roster = sample_roster(
        1,
        players=[player.player_id for player in mine],
        starters=["qb", "rb1", "rb2", "wr1", "wr2", "te", "flex"],
    )
    week_points = {
        "qb": 20,
        "rb1": 18,
        "rb2": 15,
        "wr1": 16,
        "wr2": 12,
        "te": 9,
        "flex": 10,
        "fa": 11,
    }
    ros_points = {player_id: points * 10 for player_id, points in week_points.items()}
    report = find_waivers(
        week=3,
        season="2025",
        roster=roster,
        rosters=[roster],
        players=players,
        roster_positions=league.roster_positions,
        week_points=week_points,
        ros_points=ros_points,
        trending={},
        bye_teams=set(),
        headlines={},
        scoring_settings=league.scoring_settings,
        limit=5,
    )
    assert report.adds[0].player.player_id == "fa"
    assert report.adds[0].vor_week == 1.0
