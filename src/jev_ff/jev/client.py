"""TypeSafe Jev client wrapper with a testable fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from jev_ff.errors import JevError


@dataclass
class NoulAnswer:
    noul: float
    confidence: float | None = None


@dataclass
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class ScoreAnswer:
    score: float
    confidence: float = 1.0
    legend: dict[str, str] = field(default_factory=dict)


@dataclass
class JevResult:
    nouls: dict[str, NoulAnswer] = field(default_factory=dict)
    choices: dict[str, ChoiceAnswer] = field(default_factory=dict)
    scores: dict[str, ScoreAnswer] = field(default_factory=dict)
    model: str | None = None


class JevEvaluator(Protocol):
    def system_one(self, state: Any, questions: dict[str, Any]) -> JevResult: ...


class NullJevEvaluator:
    """Deterministic fallback when no TypeSafe key is configured."""

    def system_one(self, state: Any, questions: dict[str, Any]) -> JevResult:
        result = JevResult(model="null")
        for key, question in questions.items():
            question_type = question.get("type")
            if question_type == "noul":
                result.nouls[key] = NoulAnswer(noul=0.0, confidence=0.0)
            elif question_type == "choice":
                criteria = question.get("criteria") or {}
                first = next(iter(criteria), "other")
                result.choices[key] = ChoiceAnswer(choice=str(first), probabilities={}, confidence=0.0)
            elif question_type == "score":
                result.scores[key] = ScoreAnswer(score=0.0, confidence=0.0)
        return result


class TypeSafeJevEvaluator:
    def __init__(self, api_key: str | None = None, model: str = "jev-latest") -> None:
        self.api_key = api_key
        self.model = model

    def system_one(self, state: Any, questions: dict[str, Any]) -> JevResult:
        try:
            from typesafe_sdk import TypeSafeClient, TypeSafeError
        except ImportError as exc:
            raise JevError("typesafe-sdk is not installed.") from exc

        kwargs: dict[str, Any] = {"model": self.model}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        try:
            with TypeSafeClient(**kwargs) as client:
                response = client.system_one(state=state, questions=_to_sdk_questions(questions))
        except TypeSafeError as exc:
            raise JevError(f"TypeSafe request failed: {exc}") from exc
        return result_from_sdk(response)


def _to_sdk_questions(questions: dict[str, Any]) -> dict[str, Any]:
    from typesafe_sdk import Choice, Noul, Score

    sdk_questions: dict[str, Any] = {}
    for key, question in questions.items():
        question_type = question["type"]
        if question_type == "noul":
            sdk_questions[key] = Noul(
                instructions=question["instructions"],
                criteria=question.get("criteria"),
            )
        elif question_type == "choice":
            sdk_questions[key] = Choice(
                instructions=question["instructions"],
                criteria=question["criteria"],
            )
        elif question_type == "score":
            sdk_questions[key] = Score(
                instructions=question["instructions"],
                criteria=question["criteria"],
            )
        else:
            raise ValueError(f"Unknown question type: {question_type}")
    return sdk_questions


def result_from_sdk(response: Any) -> JevResult:
    result = JevResult(model=getattr(response, "model", None))
    _copy_noul_map(result, getattr(response, "nouls", None) or {})
    _copy_choice_map(result, getattr(response, "choices", None) or {})
    _copy_score_map(result, getattr(response, "scores", None) or {})
    answers = getattr(response, "answers", None) or {}
    if answers and not (result.nouls or result.choices or result.scores):
        _copy_combined_answers(result, answers)
    return result


def _copy_noul_map(result: JevResult, nouls: dict) -> None:
    for key, answer in nouls.items():
        result.nouls[key] = NoulAnswer(
            noul=float(answer.noul),
            confidence=getattr(answer, "confidence", None),
        )


def _copy_choice_map(result: JevResult, choices: dict) -> None:
    for key, answer in choices.items():
        result.choices[key] = ChoiceAnswer(
            choice=str(answer.choice),
            probabilities=dict(getattr(answer, "probabilities", None) or {}),
            confidence=_confidence(answer, default=1.0),
        )


def _copy_score_map(result: JevResult, scores: dict) -> None:
    for key, answer in scores.items():
        legend = getattr(answer, "legend", None) or {}
        result.scores[key] = ScoreAnswer(
            score=float(answer.score),
            confidence=_confidence(answer, default=1.0),
            legend={str(level): str(label) for level, label in dict(legend).items()},
        )


def _copy_combined_answers(result: JevResult, answers: dict) -> None:
    for key, answer in answers.items():
        answer_type = getattr(answer, "type", None)
        if answer_type == "noul":
            _copy_noul_map(result, {key: answer})
        elif answer_type == "choice":
            _copy_choice_map(result, {key: answer})
        elif answer_type == "score":
            _copy_score_map(result, {key: answer})


def _confidence(answer: Any, *, default: float) -> float:
    raw = getattr(answer, "confidence", None)
    if raw is None:
        return default
    return float(raw)
