from jev_ff.sleeper.scoring import league_points

PASS_RUSH_REC = {
    "pass_yd": 300,
    "pass_td": 2,
    "rush_yd": 20,
    "rush_td": 0,
    "rec": 5,
    "rec_yd": 60,
    "rec_td": 1,
    "fum_lost": 0,
    "bonus_rec_te": 5,
}

STD = {
    "pass_yd": 0.04,
    "pass_td": 4,
    "rush_yd": 0.1,
    "rush_td": 6,
    "rec": 0,
    "rec_yd": 0.1,
    "rec_td": 6,
    "fum_lost": -2,
}
HALF = {**STD, "rec": 0.5}
PPR = {**STD, "rec": 1.0}
TE_PREM = {**PPR, "bonus_rec_te": 0.5}
PASS6 = {**PPR, "pass_td": 6}


def test_standard_ignores_receptions() -> None:
    # 300*0.04 + 2*4 + 20*0.1 + 60*0.1 + 1*6 = 12 + 8 + 2 + 6 + 6 = 34
    assert league_points(PASS_RUSH_REC, STD) == 34.0


def test_half_ppr_adds_half_per_catch() -> None:
    assert league_points(PASS_RUSH_REC, HALF) == 36.5


def test_ppr_adds_one_per_catch() -> None:
    assert league_points(PASS_RUSH_REC, PPR) == 39.0


def test_te_premium() -> None:
    assert league_points(PASS_RUSH_REC, TE_PREM) == 41.5


def test_six_point_passing_tds() -> None:
    assert league_points(PASS_RUSH_REC, PASS6) == 43.0


def test_ignores_prebaked_pts_ppr() -> None:
    stats = {**PASS_RUSH_REC, "pts_ppr": 99, "pts_std": 88}
    assert league_points(stats, STD) == 34.0


def test_empty_inputs() -> None:
    assert league_points(None, STD) == 0.0
    assert league_points(PASS_RUSH_REC, None) == 0.0
