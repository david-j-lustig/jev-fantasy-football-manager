from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import JevResult, NoulAnswer, ScoreAnswer
from jev_ff.trades.evaluator import evaluate_trade
from tests.factories import ScriptedJev, make_player, sample_roster


def test_lopsided_trade_recommends_decline() -> None:
    give = [make_player("1", "Star", "RB")]
    get = [make_player("2", "Backup", "RB")]
    report = evaluate_trade(
        week=4,
        season="2025",
        roster=sample_roster(1, players=["1"]),
        give=give,
        get=get,
        week_points={"1": 20, "2": 6},
        ros_points={"1": 180, "2": 40},
        scoring_settings={"rec": 1},
        headlines={},
    )
    assert report.ros_delta < -8
    assert "Decline" in report.recommendation


def test_jev_fairness_can_override_points() -> None:
    give = [make_player("1", "Star", "RB")]
    get = [make_player("2", "Backup", "RB")]
    result = JevResult(
        scores={"fairness": ScoreAnswer(score=1.0, confidence=0.9)},
        nouls={
            "should_accept": NoulAnswer(noul=0.2, confidence=0.8),
            "opponent_accept": NoulAnswer(noul=0.9, confidence=0.8),
        },
    )
    report = evaluate_trade(
        week=4,
        season="2025",
        roster=sample_roster(1, players=["1"]),
        give=give,
        get=get,
        week_points={"1": 20, "2": 6},
        ros_points={"1": 180, "2": 40},
        scoring_settings={"rec": 1},
        headlines={},
        advisor=JevAdvisor(ScriptedJev(result), enabled=True),
    )
    assert report.jev_enabled
    assert report.recommendation == "Jev: decline."
    assert report.fairness_label == "Slight loss"
