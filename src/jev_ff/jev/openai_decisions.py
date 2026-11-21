"""OpenAI Decisions (`gpt-6-luna`) behind the same evaluator protocol as Jev."""

from __future__ import annotations

from typing import Any

from jev_ff.errors import JevError
from jev_ff.jev.client import ChoiceAnswer, JevResult, NoulAnswer, ScoreAnswer

LUNA_MODEL = "gpt-6-luna"


def is_luna_model(model: str) -> bool:
    return model.strip().lower().startswith(LUNA_MODEL)


class OpenAIDecisionsEvaluator:
    def __init__(self, api_key: str | None = None, model: str = LUNA_MODEL) -> None:
        self.api_key = api_key
        self.model = model

    def system_one(self, state: Any, questions: dict[str, Any]) -> JevResult:
        try:
            from openai import OpenAI, OpenAIError
        except ImportError as exc:
            raise JevError("openai is not installed. Run: pip install 'jev-fantasy-football-manager[openai]'") from exc

        try:
            response = OpenAI(api_key=self.api_key).decisions.create(
                model=self.model,
                input=_to_openai_input(state),
                questions=_to_openai_questions(questions),
            )
        except OpenAIError as exc:
            raise JevError(f"OpenAI Decisions request failed: {exc}") from exc
        return result_from_openai(response)


def _to_openai_input(state: Any) -> Any:
    if isinstance(state, str):
        return state
    return [{"role": "user", "content": [{"type": "input_json", "data": state}]}]


def _to_openai_questions(questions: dict[str, Any]) -> list[dict[str, Any]]:
    converters = {"noul": _predicate, "choice": _choice, "score": _score}
    payload = []
    for name, question in questions.items():
        convert = converters.get(question["type"])
        if convert is None:
            raise ValueError(f"Unknown question type: {question['type']}")
        payload.append({"name": name, **convert(question)})
    return payload


def _predicate(question: dict[str, Any]) -> dict[str, Any]:
    # Predicates have no true/false criteria field, so they ride along in the instructions.
    criteria = question.get("criteria") or {}
    parts = [question["instructions"]]
    if criteria.get("true"):
        parts.append(f"True if: {criteria['true']}")
    if criteria.get("false"):
        parts.append(f"False if: {criteria['false']}")
    return {"type": "predicate", "instructions": " ".join(parts)}


def _choice(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": question["instructions"],
        "choices": [{"value": key, "description": text} for key, text in question["criteria"].items()],
    }


def _score(question: dict[str, Any]) -> dict[str, Any]:
    levels = []
    for text in question["criteria"]:
        label, _, description = text.partition(" — ")
        levels.append({"label": label, "description": description} if description else {"label": text})
    return {"type": "score", "instructions": question["instructions"], "levels": levels}


def result_from_openai(response: Any) -> JevResult:
    result = JevResult(model=response.model)
    for answer in response.answers:
        if answer.name is None:
            continue
        if answer.type == "predicate":
            result.nouls[answer.name] = NoulAnswer(noul=answer.probability)
        elif answer.type == "choice":
            result.choices[answer.name] = ChoiceAnswer(
                choice=str(answer.choice),
                probabilities={str(item.value): item.probability for item in answer.probabilities},
                confidence=answer.confidence,
            )
        elif answer.type == "score":
            result.scores[answer.name] = ScoreAnswer(score=answer.score, confidence=answer.confidence)
    return result
