from types import SimpleNamespace

import pytest
import typesafe_sdk
from typesafe_sdk import TypeSafeAPIConnectionError

from jev_ff.errors import JevError
from jev_ff.jev.advisor import JevAdvisor
from jev_ff.jev.client import (
    ChoiceAnswer,
    JevResult,
    NoulAnswer,
    ScoreAnswer,
    TypeSafeJevEvaluator,
    result_from_sdk,
)
from jev_ff.lineup.optimizer import PlayerValue, optimize_lineup
from tests.factories import ScriptedJev, make_player_value


def _overlay(
    pool: list[PlayerValue],
    slots: list[str],
    result: JevResult,
    headlines: dict[str, list[str]] | None = None,
) -> tuple[list[PlayerValue], list[str]]:
    advisor = JevAdvisor(ScriptedJev(result), enabled=True)
    adjusted, notes, _ = advisor.overlay_lineup(
        week=1,
        scoring_settings={"rec": 0.5},
        solution=optimize_lineup(slots, pool),
        pool=pool,
        headlines=headlines or {},
        opponents={},
    )
    return adjusted, notes


def test_confident_inactive_sits_the_starter() -> None:
    starter = make_player_value("1", "Q Star", "QB", 20, injury_status="Questionable", injury_notes="ankle")
    backup = make_player_value("2", "Q Two", "QB", 12)
    pool = [starter, backup]
    result = JevResult(
        nouls={"inactive_1": NoulAnswer(noul=0.91, confidence=0.8)},
        scores={"discount_1": ScoreAnswer(score=3, confidence=0.8)},
    )
    adjusted, notes = _overlay(pool, ["QB"], result, headlines={"1": ["Ankle sprain, not practicing"]})
    values_by_id = {value.player_id: value for value in adjusted}
    assert values_by_id["1"].eligible is False
    assert values_by_id["1"].points == 0
    assert any("inactive" in note.lower() for note in notes)
    rerun = optimize_lineup(["QB"], adjusted)
    assert rerun.assignments[0][1].player.player_id == "2"


def test_low_confidence_inactive_does_not_sit() -> None:
    starter = make_player_value("1", "Q Star", "QB", 20, injury_status="Questionable")
    backup = make_player_value("2", "Q Two", "QB", 12)
    result = JevResult(
        nouls={"inactive_1": NoulAnswer(noul=0.91, confidence=0.1)},
        scores={"discount_1": ScoreAnswer(score=3, confidence=0.1)},
    )
    adjusted, notes = _overlay(
        [starter, backup],
        ["QB"],
        result,
        headlines={"1": ["Questionable"]},
    )
    values_by_id = {value.player_id: value for value in adjusted}
    assert values_by_id["1"].eligible is True
    assert values_by_id["1"].points == 20
    assert values_by_id["1"].needs_review
    assert any("review" in note.lower() for note in notes)


def test_start_sit_choice_promotes_the_backup() -> None:
    starter = make_player_value("a", "Starter Back", "RB", 14)
    sitter = make_player_value("b", "Sitter Back", "RB", 13)
    result = JevResult(
        choices={"start_0_RB": ChoiceAnswer(choice="b", confidence=0.8, probabilities={"a": 0.2, "b": 0.8})},
    )
    adjusted, notes = _overlay([starter, sitter], ["RB"], result)
    rerun = optimize_lineup(["RB"], adjusted)
    assert rerun.assignments[0][1].player.player_id == "b"
    assert any("prefers" in note.lower() for note in notes)


def test_low_confidence_start_sit_flags_review_on_adjusted_starter() -> None:
    starter = make_player_value("a", "Starter Back", "RB", 14)
    sitter = make_player_value("b", "Sitter Back", "RB", 13)
    result = JevResult(
        choices={"start_0_RB": ChoiceAnswer(choice="b", confidence=0.1, probabilities={"a": 0.4, "b": 0.6})},
    )
    adjusted, notes = _overlay([starter, sitter], ["RB"], result)
    values_by_id = {value.player_id: value for value in adjusted}
    assert values_by_id["a"].needs_review
    assert values_by_id["a"].points == 14
    assert starter.needs_review is False
    assert any("review" in note.lower() for note in notes)


def test_sdk_zero_confidence_is_preserved() -> None:
    response = SimpleNamespace(
        model="jev",
        nouls={},
        choices={"start": SimpleNamespace(choice="a", probabilities={}, confidence=0.0)},
        scores={"faab": SimpleNamespace(score=2.0, confidence=0.0, legend={})},
        answers={},
    )
    result = result_from_sdk(response)
    assert result.choices["start"].confidence == 0.0
    assert result.scores["faab"].confidence == 0.0


def test_typesafe_connection_error_is_jev_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def system_one(self, **kwargs: object):
            raise TypeSafeAPIConnectionError("offline")

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", FakeClient)
    evaluator = TypeSafeJevEvaluator(api_key="test-key", model="jev-latest")
    with pytest.raises(JevError, match="TypeSafe request failed"):
        evaluator.system_one({}, {"inactive": {"type": "noul", "instructions": "Is this player inactive?"}})
