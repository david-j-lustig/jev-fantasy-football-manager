from tests.factories import ScriptedJev, make_player

from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import ChoiceAnswer, JevResult, NoulAnswer, ScoreAnswer
from jev_ff.lineup.optimizer import PlayerValue, optimize_lineup


def _pv(pid: str, name: str, pos: str, pts: float, **kwargs) -> PlayerValue:
    return PlayerValue(player=make_player(pid, name, pos, **kwargs), points=pts, eligible=True)


def test_inactive_sits_player() -> None:
    starter = _pv("1", "Q Star", "QB", 20, injury_status="Questionable", injury_notes="ankle")
    backup = _pv("2", "Q Two", "QB", 12)
    pool = [starter, backup]
    solution = optimize_lineup(["QB"], pool)
    result = JevResult(
        nouls={"inactive_1": NoulAnswer(noul=0.91, confidence=0.8)},
        scores={"discount_1": ScoreAnswer(score=3, confidence=0.8)},
    )
    advisor = JevAdvisor(ScriptedJev(result), enabled=True)
    adjusted, notes, _ = advisor.overlay_lineup(
        week=1,
        scoring_settings={"rec": 0.5},
        solution=solution,
        pool=pool,
        headlines={"1": ["Ankle sprain, not practicing"]},
        opponents={},
    )
    by_id = {pv.player_id: pv for pv in adjusted}
    assert by_id["1"].eligible is False
    assert by_id["1"].points == 0
    assert any("inactive" in note.lower() for note in notes)
    rerun = optimize_lineup(["QB"], adjusted)
    assert rerun.assignments[0][1].player.player_id == "2"


def test_low_confidence_does_not_sit() -> None:
    starter = _pv("1", "Q Star", "QB", 20, injury_status="Questionable")
    backup = _pv("2", "Q Two", "QB", 12)
    pool = [starter, backup]
    solution = optimize_lineup(["QB"], pool)
    result = JevResult(
        nouls={"inactive_1": NoulAnswer(noul=0.91, confidence=0.1)},
        scores={"discount_1": ScoreAnswer(score=3, confidence=0.1)},
    )
    advisor = JevAdvisor(ScriptedJev(result), enabled=True)
    adjusted, notes, _ = advisor.overlay_lineup(
        week=1,
        scoring_settings={"rec": 0.5},
        solution=solution,
        pool=pool,
        headlines={"1": ["Questionable"]},
        opponents={},
    )
    by_id = {pv.player_id: pv for pv in adjusted}
    assert by_id["1"].eligible is True
    assert by_id["1"].points == 20
    assert by_id["1"].needs_review
    assert any("review" in note.lower() for note in notes)


def test_start_sit_choice_promotes_backup() -> None:
    rb1 = _pv("a", "Starter Back", "RB", 14)
    rb2 = _pv("b", "Sitter Back", "RB", 13)
    pool = [rb1, rb2]
    solution = optimize_lineup(["RB"], pool)
    result = JevResult(
        choices={"start_0_RB": ChoiceAnswer(choice="b", confidence=0.8, probabilities={"a": 0.2, "b": 0.8})},
    )
    advisor = JevAdvisor(ScriptedJev(result), enabled=True)
    adjusted, notes, _ = advisor.overlay_lineup(
        week=1,
        scoring_settings={"rec": 0.5},
        solution=solution,
        pool=pool,
        headlines={},
        opponents={},
    )
    rerun = optimize_lineup(["RB"], adjusted)
    assert rerun.assignments[0][1].player.player_id == "b"
    assert any("prefers" in note.lower() for note in notes)
