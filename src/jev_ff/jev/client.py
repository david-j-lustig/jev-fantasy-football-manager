"""TypeSafe Jev client wrapper with a testable fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


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
            qtype = question.get("type")
            if qtype == "noul":
                result.nouls[key] = NoulAnswer(noul=0.0, confidence=0.0)
            elif qtype == "choice":
                criteria = question.get("criteria") or {}
                first = next(iter(criteria), "other")
                result.choices[key] = ChoiceAnswer(choice=str(first), probabilities={}, confidence=0.0)
            elif qtype == "score":
                result.scores[key] = ScoreAnswer(score=0.0, confidence=0.0)
        return result


class TypeSafeJevEvaluator:
    def __init__(self, api_key: str | None = None, model: str = "jev-latest") -> None:
        self.api_key = api_key
        self.model = model

    def system_one(self, state: Any, questions: dict[str, Any]) -> JevResult:
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

        sdk_questions: dict[str, Any] = {}
        for key, question in questions.items():
            qtype = question["type"]
            if qtype == "noul":
                sdk_questions[key] = Noul(
                    instructions=question["instructions"],
                    criteria=question.get("criteria"),
                )
            elif qtype == "choice":
                sdk_questions[key] = Choice(
                    instructions=question["instructions"],
                    criteria=question["criteria"],
                )
            elif qtype == "score":
                sdk_questions[key] = Score(
                    instructions=question["instructions"],
                    criteria=question["criteria"],
                )
            else:
                raise ValueError(f"Unknown question type: {qtype}")

        kwargs: dict[str, Any] = {"model": self.model}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        with TypeSafeClient(**kwargs) as client:
            response = client.system_one(state=state, questions=sdk_questions)
        return _from_sdk(response)


def _from_sdk(response: Any) -> JevResult:
    result = JevResult(model=getattr(response, "model", None))
    nouls = getattr(response, "nouls", None) or {}
    choices = getattr(response, "choices", None) or {}
    scores = getattr(response, "scores", None) or {}
    for key, answer in nouls.items():
        result.nouls[key] = NoulAnswer(
            noul=float(answer.noul),
            confidence=getattr(answer, "confidence", None),
        )
    for key, answer in choices.items():
        result.choices[key] = ChoiceAnswer(
            choice=str(answer.choice),
            probabilities=dict(getattr(answer, "probabilities", None) or {}),
            confidence=float(getattr(answer, "confidence", 1.0) or 1.0),
        )
    for key, answer in scores.items():
        legend = getattr(answer, "legend", None) or {}
        result.scores[key] = ScoreAnswer(
            score=float(answer.score),
            confidence=float(getattr(answer, "confidence", 1.0) or 1.0),
            legend={str(k): str(v) for k, v in dict(legend).items()},
        )
    # Some SDK versions expose a combined `.answers` map instead.
    answers = getattr(response, "answers", None) or {}
    if answers and not (result.nouls or result.choices or result.scores):
        for key, answer in answers.items():
            atype = getattr(answer, "type", None)
            if atype == "noul":
                result.nouls[key] = NoulAnswer(noul=float(answer.noul), confidence=getattr(answer, "confidence", None))
            elif atype == "choice":
                result.choices[key] = ChoiceAnswer(
                    choice=str(answer.choice),
                    probabilities=dict(getattr(answer, "probabilities", None) or {}),
                    confidence=float(getattr(answer, "confidence", 1.0) or 1.0),
                )
            elif atype == "score":
                result.scores[key] = ScoreAnswer(
                    score=float(answer.score),
                    confidence=float(getattr(answer, "confidence", 1.0) or 1.0),
                )
    return result
