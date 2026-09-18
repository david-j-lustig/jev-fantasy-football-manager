"""Apply Jev judgments onto projection-based player values."""

from __future__ import annotations

from jev_ff.jev.client import JevEvaluator, JevResult, NullJevEvaluator
from jev_ff.jev.questions import lineup as lineup_q
from jev_ff.jev.questions import trades as trades_q
from jev_ff.jev.questions import waivers as waivers_q
from jev_ff.jev.state import card_from_value, lineup_state, player_card, scoring_summary
from jev_ff.lineup.optimizer import LineupSolution, PlayerValue, close_calls
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

        newsy = [pv for pv in pool if pv.player.injury_status or headlines.get(pv.player_id)]
        calls = close_calls(solution, pool)
        if not newsy and not calls:
            return pool, [], None

        cards = [
            card_from_value(
                pv,
                opponent=opponents.get(pv.player_id),
                headlines=headlines.get(pv.player_id, []),
            )
            for pv in pool
            if pv.player_id in {p.player_id for p in newsy}
            or any(pv.player_id == c["starter"].player_id or pv in c["sitters"] for c in calls)
        ]
        close_payload = []
        questions: dict = {}
        for pv in newsy:
            questions[f"inactive_{pv.player_id}"] = lineup_q.inactive_question(pv.player.full_name)
            questions[f"discount_{pv.player_id}"] = lineup_q.discount_question(pv.player.full_name)
        for i, call in enumerate(calls):
            options = [call["starter"], *call["sitters"]]
            names = {opt.player_id: opt.player.full_name for opt in options}
            questions[f"start_{i}_{call['slot']}"] = lineup_q.start_sit_question(call["slot"], names)
            close_payload.append(
                {
                    "slot": call["slot"],
                    "candidates": [names[pid] for pid in names],
                }
            )

        state = lineup_state(
            week=week,
            scoring_summary=scoring_summary(scoring_settings),
            players=cards,
            close_calls=close_payload,
        )
        result = self.evaluator.system_one(state, questions)
        adjusted = {pv.player_id: _clone_value(pv) for pv in pool}
        notes: list[str] = []

        for pv in newsy:
            pid = pv.player_id
            noul = result.nouls.get(f"inactive_{pid}")
            if noul and noul.noul >= INACTIVE_THRESHOLD and _confident(noul.confidence):
                adjusted[pid].points = 0.0
                adjusted[pid].eligible = False
                adjusted[pid].reason = "Jev: likely inactive"
                notes.append(f"{pv.player.full_name}: Jev thinks inactive ({noul.noul:.2f}).")
                continue
            if noul and noul.noul >= INACTIVE_THRESHOLD and not _confident(noul.confidence):
                adjusted[pid].needs_review = True
                notes.append(f"{pv.player.full_name}: possible inactive, low confidence — review.")
            score = result.scores.get(f"discount_{pid}")
            if score and _confident(score.confidence):
                factor = _discount_factor(score.score)
                adjusted[pid].points = round(adjusted[pid].points * factor, 4)
                if factor < 1:
                    adjusted[pid].reason = f"Jev discount x{factor:.2f}"
                    notes.append(f"{pv.player.full_name}: projection discounted x{factor:.2f}.")
            elif score and not _confident(score.confidence):
                adjusted[pid].needs_review = True

        for i, call in enumerate(calls):
            key = f"start_{i}_{call['slot']}"
            choice = result.choices.get(key)
            if not choice or choice.choice == "other":
                continue
            if not _confident(choice.confidence):
                call["starter"].needs_review = True
                notes.append(f"{call['slot']}: start/sit needs review (low Jev confidence).")
                continue
            chosen = adjusted.get(choice.choice)
            starter = adjusted.get(call["starter"].player_id)
            if chosen is None or starter is None or chosen.player_id == starter.player_id:
                continue
            if chosen.points <= starter.points:
                chosen.points = round(starter.points + 0.01, 4)
                chosen.reason = f"Jev start/sit over {starter.player.full_name}"
                notes.append(f"{call['slot']}: Jev prefers {chosen.player.full_name} over {starter.player.full_name}.")

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
        drop_names = {player.player_id: player.full_name for player, _ in drops[:5]}
        questions: dict = {}
        cards = []
        primary_drop = drops[0][0] if drops else None
        for player, week_pts, ros_pts in adds:
            cards.append(
                player_card(
                    player,
                    projected_points=week_pts,
                    ros_points=ros_pts,
                    headlines=headlines.get(player.player_id, []),
                )
            )
            drop_name = primary_drop.full_name if primary_drop else "a bench player"
            questions[f"worth_{player.player_id}"] = waivers_q.add_worth_it_question(player.full_name, drop_name)
            questions[f"faab_{player.player_id}"] = waivers_q.faab_question(player.full_name)
        if drop_names:
            questions["best_drop"] = waivers_q.best_drop_question(drop_names)
        state = {
            "week": week,
            "scoring": scoring_summary(scoring_settings),
            "adds": cards,
            "drops": [
                player_card(player, projected_points=pts, headlines=headlines.get(player.player_id, []))
                for player, pts in drops[:5]
            ],
        }
        return self.evaluator.system_one(state, questions)

    def evaluate_trade(self, state: dict) -> JevResult | None:
        if not self.enabled:
            return None
        questions = {
            "fairness": trades_q.fairness_question(),
            "should_accept": trades_q.should_accept_question(),
            "opponent_accept": trades_q.opponent_accept_question(),
        }
        return self.evaluator.system_one(state, questions)


def _clone_value(pv: PlayerValue) -> PlayerValue:
    return PlayerValue(
        player=pv.player,
        points=pv.points,
        on_bye=pv.on_bye,
        out=pv.out,
        reason=pv.reason,
        needs_review=pv.needs_review,
        eligible=pv.eligible,
    )


def _confident(confidence: float | None) -> bool:
    if confidence is None:
        return True
    return confidence >= CONFIDENCE_FLOOR


def _discount_factor(score: float) -> float:
    bounded = max(0.0, min(3.0, float(score)))
    lo = int(bounded)
    hi = min(3, lo + 1)
    frac = bounded - lo
    return DISCOUNT_MULTIPLIERS[lo] * (1 - frac) + DISCOUNT_MULTIPLIERS[hi] * frac
