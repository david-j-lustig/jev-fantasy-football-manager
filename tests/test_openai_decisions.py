import json

import httpx
import openai
import pytest

from jev_ff.errors import ConfigError, JevError
from jev_ff.jev.client import NullJevEvaluator, TypeSafeJevEvaluator
from jev_ff.jev.openai_decisions import OpenAIDecisionsEvaluator
from jev_ff.jev.questions import lineup, trades
from jev_ff.manager import _build_jev_evaluator

USAGE = {
    "input_tokens": 1,
    "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
    "output_tokens": 0,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 1,
}


def _mock_openai(monkeypatch, handler) -> None:
    real_client = openai.OpenAI
    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    def client(api_key=None):
        return real_client(api_key=api_key, max_retries=0, http_client=http_client)

    monkeypatch.setattr(openai, "OpenAI", client)


def test_round_trip_through_openai_sdk(monkeypatch) -> None:
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-6-luna",
                "usage": USAGE,
                "answers": [
                    {"type": "predicate", "name": "inactive", "probability": 0.82},
                    {
                        "type": "choice",
                        "name": "start",
                        "choice": "b",
                        "confidence": 0.9,
                        "probabilities": [{"value": "a", "probability": 0.2}, {"value": "b", "probability": 0.8}],
                    },
                    {"type": "refusal", "name": "fairness"},
                ],
            },
        )

    _mock_openai(monkeypatch, handler)
    result = OpenAIDecisionsEvaluator(api_key="sk-test").system_one(
        {"week": 3},
        {
            "inactive": lineup.inactive_question("Q Star"),
            "start": lineup.start_sit_question("RB", {"a": "A Back", "b": "B Back"}),
            "fairness": trades.fairness_question(),
        },
    )

    questions = {question["name"]: question for question in sent["questions"]}
    assert sent["input"] == [{"role": "user", "content": [{"type": "input_json", "data": {"week": 3}}]}]
    assert "True if: Ruled out" in questions["inactive"]["instructions"]
    assert [choice["value"] for choice in questions["start"]["choices"]] == ["a", "b", "other"]
    assert questions["fairness"]["levels"][0] == {"label": "Bad trade", "description": "a clear loss for this roster."}

    assert result.nouls["inactive"].noul == 0.82
    assert result.choices["start"].choice == "b"
    assert result.choices["start"].probabilities == {"a": 0.2, "b": 0.8}
    assert "fairness" not in result.scores


def test_openai_api_error_becomes_jev_error(monkeypatch) -> None:
    _mock_openai(monkeypatch, lambda request: httpx.Response(400, json={"error": {"message": "bad question"}}))
    with pytest.raises(JevError, match="OpenAI Decisions request failed"):
        OpenAIDecisionsEvaluator(api_key="sk-test").system_one({"week": 1}, {"inactive": lineup.inactive_question("Q")})


@pytest.mark.parametrize(
    ("model", "typesafe_key", "openai_key", "expected"),
    [
        ("gpt-6-luna", None, "sk-test", OpenAIDecisionsEvaluator),
        ("jev-latest", "ts-key", "sk-test", TypeSafeJevEvaluator),
        ("jev-latest", None, "sk-test", NullJevEvaluator),
    ],
)
def test_model_picks_backend(model, typesafe_key, openai_key, expected) -> None:
    assert isinstance(_build_jev_evaluator(None, typesafe_key, openai_key, model), expected)


def test_luna_without_openai_key_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        _build_jev_evaluator(None, "ts-key", None, "gpt-6-luna")
