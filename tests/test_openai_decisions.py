import sys
from types import SimpleNamespace

import pytest

from jev_ff.errors import ConfigError, JevError
from jev_ff.jev.client import NullJevEvaluator, TypeSafeJevEvaluator
from jev_ff.jev.openai_decisions import (
    OpenAIDecisionsEvaluator,
    _to_openai_input,
    _to_openai_questions,
    result_from_openai,
)
from jev_ff.jev.questions import lineup, trades, waivers
from jev_ff.manager import _build_jev_evaluator


def test_questions_convert_to_openai_shape() -> None:
    converted = _to_openai_questions(
        {
            "inactive": lineup.inactive_question("Q Star"),
            "start": lineup.start_sit_question("RB", {"a": "A Back", "b": "B Back"}),
            "fairness": trades.fairness_question(),
            "faab": waivers.faab_question("W Add"),
        }
    )
    by_name = {item["name"]: item for item in converted}

    assert by_name["inactive"]["type"] == "predicate"
    assert "True if: Ruled out" in by_name["inactive"]["instructions"]
    assert "False if: Expected to play" in by_name["inactive"]["instructions"]

    assert [choice["value"] for choice in by_name["start"]["choices"]] == ["a", "b", "other"]

    fairness_levels = by_name["fairness"]["levels"]
    assert len(fairness_levels) == 5
    assert fairness_levels[0] == {"label": "Bad trade", "description": "a clear loss for this roster."}
    assert by_name["faab"]["levels"][0]["label"] == "Ignore / $0"


def test_dict_state_is_sent_as_input_json() -> None:
    assert _to_openai_input({"week": 3}) == [{"role": "user", "content": [{"type": "input_json", "data": {"week": 3}}]}]
    assert _to_openai_input("plain text") == "plain text"


def test_result_from_openai_maps_answers_and_skips_refusals() -> None:
    response = SimpleNamespace(
        model="gpt-6-luna",
        answers=[
            SimpleNamespace(type="predicate", name="inactive", probability=0.82),
            SimpleNamespace(
                type="choice",
                name="start",
                choice="b",
                confidence=0.9,
                probabilities=[
                    SimpleNamespace(value="a", probability=0.2),
                    SimpleNamespace(value="b", probability=0.8),
                ],
            ),
            SimpleNamespace(type="score", name="faab", score=2.4, confidence=0.6, probabilities=[]),
            SimpleNamespace(type="refusal", name="fairness"),
        ],
    )
    result = result_from_openai(response)
    assert result.model == "gpt-6-luna"
    assert result.nouls["inactive"].noul == 0.82
    assert result.nouls["inactive"].confidence is None
    assert result.choices["start"].choice == "b"
    assert result.choices["start"].probabilities == {"a": 0.2, "b": 0.8}
    assert result.scores["faab"].score == 2.4
    assert "fairness" not in result.scores


def test_openai_error_becomes_jev_error(monkeypatch) -> None:
    class FakeOpenAIError(Exception):
        pass

    class FakeDecisions:
        def create(self, **kwargs: object):
            raise FakeOpenAIError("offline")

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.decisions = FakeDecisions()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeClient, OpenAIError=FakeOpenAIError))
    evaluator = OpenAIDecisionsEvaluator(api_key="sk-test")
    with pytest.raises(JevError, match="OpenAI Decisions request failed"):
        evaluator.system_one({"week": 1}, {"inactive": lineup.inactive_question("Q Star")})


def test_luna_model_selects_openai_backend() -> None:
    evaluator = _build_jev_evaluator(None, None, "sk-test", "gpt-6-luna")
    assert isinstance(evaluator, OpenAIDecisionsEvaluator)
    assert evaluator.model == "gpt-6-luna"


def test_luna_model_without_openai_key_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        _build_jev_evaluator(None, "ts-key", None, "gpt-6-luna")


def test_jev_model_ignores_openai_key() -> None:
    assert isinstance(
        _build_jev_evaluator(None, "ts-key", "sk-test", "jev-latest"),
        TypeSafeJevEvaluator,
    )
    assert isinstance(
        _build_jev_evaluator(None, None, "sk-test", "jev-latest"),
        NullJevEvaluator,
    )
