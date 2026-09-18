"""Apply Jev judgments onto projection-based player values."""

from __future__ import annotations

from typing import Any

from jev_ff.jev.client import JevEvaluator, JevResult, NullJevEvaluator
from jev_ff.jev.questions import lineup as lineup_questions
from jev_ff.jev.questions import trades as trade_questions
from jev_ff.jev.questions import waivers as waiver_questions
from jev_ff.jev.state import card_from_value, lineup_state, player_card, scoring_summary
from jev_ff.lineup.optimizer import CloseCall, LineupSolution, PlayerValue, find_close_calls
from jev_ff.sleeper.models import Player

DISCOUNT_MULTIPLIERS = [1.0, 0.85, 0.5, 0.0]
INACTIVE_THRESHOLD = 0.7
CONFIDENCE_FLOOR = 0.45


class JevAdvisor:
    def __init__(self, evaluator: JevEvaluator | None = None, *, enabled: bool = True) -> None:
        self.evaluator = evaluator or NullJevEvaluator()
        self.enabled = enabled and not isinstance(self.evaluator, NullJevEvaluator)

    def overlay_lineup(
        self,
        *,
        week: int,
        scoring_settings: dict[str, float],
        solution: LineupSolution,
        pool: list[PlayerValue],
        headlines: dict[str, list[str]],
        opponents: dict[str, str | None],
    ) -> tuple[list[PlayerValue], list[str], JevResult | None]:
        if not self.enabled:
            return pool, [], None

        newsworthy = _newsworthy_players(pool, headlines)
        close_calls = find_close_calls(solution, pool)
        if not newsworthy and not close_calls:
            return pool, [], None

        questions, state = _lineup_request(
            week=week,
            scoring_settings=scoring_settings,
            pool=pool,
            newsworthy=newsworthy,
            close_calls=close_calls,
            headlines=headlines,
            opponents=opponents,
        )
        result = self.evaluator.system_one(state, questions)
        adjusted = {value.player_id: value.copy() for value in pool}
        notes: list[str] = []
        _apply_injury_answers(adjusted, newsworthy, result, notes)
        _apply_start_sit_answers(adjusted, close_calls, result, notes)
        return list(adjusted.values()), notes, result

    def evaluate_waivers(
        self,
        *,
        week: int,
        scoring_settings: dict[str, float],
        adds: list[tuple[Player, float, float]],
        drops: list[tuple[Player, float]],
        headlines: dict[str, list[str]],
    ) -> JevResult | None:
        if not self.enabled or not adds:
            return None
        questions, state = _waiver_request(
            week=week,
            scoring_settings=scoring_settings,
            adds=adds,
            drops=drops,
            headlines=headlines,
        )
        return self.evaluator.system_one(state, questions)

    def evaluate_trade(self, state: dict) -> JevResult | None:
        if not self.enabled:
            return None
        questions = {
            "fairness": trade_questions.fairness_question(),
            "should_accept": trade_questions.should_accept_question(),
            "opponent_accept": trade_questions.opponent_accept_question(),
        }
        return self.evaluator.system_one(state, questions)


def _newsworthy_players(pool: list[PlayerValue], headlines: dict[str, list[str]]) -> list[PlayerValue]:
    return [value for value in pool if value.player.injury_status or headlines.get(value.player_id)]


def _lineup_request(
    *,
    week: int,
    scoring_settings: dict[str, float],
    pool: list[PlayerValue],
    newsworthy: list[PlayerValue],
    close_calls: list[CloseCall],
    headlines: dict[str, list[str]],
    opponents: dict[str, str | None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    involved_ids = {value.player_id for value in newsworthy}
    for call in close_calls:
        involved_ids.add(call.starter.player_id)
        involved_ids.update(sitter.player_id for sitter in call.sitters)

    cards = [
        card_from_value(
            value,
            opponent=opponents.get(value.player_id),
            headlines=headlines.get(value.player_id, []),
        )
        for value in pool
        if value.player_id in involved_ids
    ]
    questions: dict[str, Any] = {}
    for value in newsworthy:
        questions[f"inactive_{value.player_id}"] = lineup_questions.inactive_question(value.player.full_name)
        questions[f"discount_{value.player_id}"] = lineup_questions.discount_question(value.player.full_name)
    close_payload = _add_start_sit_questions(questions, close_calls)
    state = lineup_state(
        week=week,
        scoring_summary=scoring_summary(scoring_settings),
        players=cards,
        close_calls=close_payload,
    )
    return questions, state


def _add_start_sit_questions(questions: dict[str, Any], close_calls: list[CloseCall]) -> list[dict[str, Any]]:
    close_payload = []
    for index, call in enumerate(close_calls):
        names = {candidate.player_id: candidate.player.full_name for candidate in [call.starter, *call.sitters]}
        questions[f"start_{index}_{call.slot}"] = lineup_questions.start_sit_question(call.slot, names)
        close_payload.append({"slot": call.slot, "candidates": list(names.values())})
    return close_payload


def _apply_injury_answers(
    adjusted: dict[str, PlayerValue],
    newsworthy: list[PlayerValue],
    result: JevResult,
    notes: list[str],
) -> None:
    for value in newsworthy:
        player_id = value.player_id
        inactive = result.nouls.get(f"inactive_{player_id}")
        if inactive and inactive.noul >= INACTIVE_THRESHOLD and _is_confident(inactive.confidence):
            adjusted[player_id].points = 0.0
            adjusted[player_id].eligible = False
            adjusted[player_id].reason = "Jev: likely inactive"
            notes.append(f"{value.player.full_name}: Jev thinks inactive ({inactive.noul:.2f}).")
            continue
        if inactive and inactive.noul >= INACTIVE_THRESHOLD and not _is_confident(inactive.confidence):
            adjusted[player_id].needs_review = True
            notes.append(f"{value.player.full_name}: possible inactive, low confidence — review.")
        discount = result.scores.get(f"discount_{player_id}")
        if discount and _is_confident(discount.confidence):
            factor = _discount_factor(discount.score)
            adjusted[player_id].points = round(adjusted[player_id].points * factor, 4)
            if factor < 1:
                adjusted[player_id].reason = f"Jev discount x{factor:.2f}"
                notes.append(f"{value.player.full_name}: projection discounted x{factor:.2f}.")
        elif discount and not _is_confident(discount.confidence):
            adjusted[player_id].needs_review = True


def _apply_start_sit_answers(
    adjusted: dict[str, PlayerValue],
    close_calls: list[CloseCall],
    result: JevResult,
    notes: list[str],
) -> None:
    for index, call in enumerate(close_calls):
        choice = result.choices.get(f"start_{index}_{call.slot}")
        if not choice or choice.choice == "other":
            continue
        if not _is_confident(choice.confidence):
            call.starter.needs_review = True
            notes.append(f"{call.slot}: start/sit needs review (low Jev confidence).")
            continue
        chosen = adjusted.get(choice.choice)
        starter = adjusted.get(call.starter.player_id)
        if chosen is None or starter is None or chosen.player_id == starter.player_id:
            continue
        if chosen.points <= starter.points:
            chosen.points = round(starter.points + 0.01, 4)
            chosen.reason = f"Jev start/sit over {starter.player.full_name}"
            notes.append(f"{call.slot}: Jev prefers {chosen.player.full_name} over {starter.player.full_name}.")


def _waiver_request(
    *,
    week: int,
    scoring_settings: dict[str, float],
    adds: list[tuple[Player, float, float]],
    drops: list[tuple[Player, float]],
    headlines: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    drop_names = {player.player_id: player.full_name for player, _ in drops[:5]}
    primary_drop = drops[0][0] if drops else None
    questions: dict[str, Any] = {}
    add_cards = []
    for player, week_points, ros_points in adds:
        add_cards.append(
            player_card(
                player,
                projected_points=week_points,
                ros_points=ros_points,
                headlines=headlines.get(player.player_id, []),
            )
        )
        drop_name = primary_drop.full_name if primary_drop else "a bench player"
        questions[f"worth_{player.player_id}"] = waiver_questions.add_worth_it_question(player.full_name, drop_name)
        questions[f"faab_{player.player_id}"] = waiver_questions.faab_question(player.full_name)
    if drop_names:
        questions["best_drop"] = waiver_questions.best_drop_question(drop_names)
    state = {
        "week": week,
        "scoring": scoring_summary(scoring_settings),
        "adds": add_cards,
        "drops": [
            player_card(
                player,
                projected_points=points,
                headlines=headlines.get(player.player_id, []),
            )
            for player, points in drops[:5]
        ],
    }
    return questions, state


def _is_confident(confidence: float | None) -> bool:
    if confidence is None:
        return True
    return confidence >= CONFIDENCE_FLOOR


def _discount_factor(score: float) -> float:
    bounded = max(0.0, min(3.0, float(score)))
    low = int(bounded)
    high = min(3, low + 1)
    fraction = bounded - low
    return DISCOUNT_MULTIPLIERS[low] * (1 - fraction) + DISCOUNT_MULTIPLIERS[high] * fraction
