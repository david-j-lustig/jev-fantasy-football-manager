import pytest

from jev_ff.sleeper.scoring import league_points

STATS = {
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

STANDARD = {
    "pass_yd": 0.04,
    "pass_td": 4,
    "rush_yd": 0.1,
    "rush_td": 6,
    "rec": 0,
    "rec_yd": 0.1,
    "rec_td": 6,
    "fum_lost": -2,
}
HALF_PPR = {**STANDARD, "rec": 0.5}
PPR = {**STANDARD, "rec": 1.0}
TE_PREMIUM = {**PPR, "bonus_rec_te": 0.5}
SIX_POINT_PASSING = {**PPR, "pass_td": 6}


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (STANDARD, 34.0),
        (HALF_PPR, 36.5),
        (PPR, 39.0),
        (TE_PREMIUM, 41.5),
        (SIX_POINT_PASSING, 43.0),
    ],
)
def test_league_points_uses_this_leagues_settings(settings: dict, expected: float) -> None:
    assert league_points(STATS, settings) == expected


def test_ignores_prebaked_totals_and_empty_inputs() -> None:
    stats_with_prebaked = {**STATS, "pts_ppr": 99, "pts_std": 88}
    assert league_points(stats_with_prebaked, STANDARD) == 34.0
    assert league_points(None, STANDARD) == 0.0
    assert league_points(STATS, None) == 0.0
