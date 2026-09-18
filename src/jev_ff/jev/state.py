"""Compact JSON state for Jev. Send only what the questions need."""

from __future__ import annotations

from typing import Any

from jev_ff.lineup.optimizer import PlayerValue
from jev_ff.sleeper.models import Player


def player_card(
    player: Player,
    *,
    projected_points: float,
    opponent: str | None = None,
    headlines: list[str] | None = None,
    ros_points: float | None = None,
) -> dict[str, Any]:
    return {
        "id": player.player_id,
        "name": player.full_name,
        "team": player.team,
        "positions": player.positions,
        "injury_status": player.injury_status,
        "practice_participation": player.practice_participation,
        "injury_notes": player.injury_notes,
        "projected_points": round(projected_points, 2),
        "ros_points": None if ros_points is None else round(ros_points, 2),
        "opponent": opponent,
        "headlines": headlines or [],
    }


def card_from_value(
    pv: PlayerValue,
    *,
    opponent: str | None = None,
    headlines: list[str] | None = None,
) -> dict[str, Any]:
    return player_card(
        pv.player,
        projected_points=pv.points,
        opponent=opponent,
        headlines=headlines,
    )


def lineup_state(
    *,
    week: int,
    scoring_summary: str,
    players: list[dict[str, Any]],
    close_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "week": week,
        "scoring": scoring_summary,
        "players": players,
        "close_calls": close_calls,
    }


def scoring_summary(scoring_settings: dict[str, float]) -> str:
    rec = float(scoring_settings.get("rec") or 0)
    pass_td = float(scoring_settings.get("pass_td") or 0)
    te_bonus = float(scoring_settings.get("bonus_rec_te") or 0)
    if rec >= 0.9:
        ppr = "PPR"
    elif rec >= 0.4:
        ppr = "half-PPR"
    else:
        ppr = "standard"
    bits = [ppr, f"{pass_td:g}-pt passing TDs"]
    if te_bonus:
        bits.append(f"TE premium +{te_bonus:g}/rec")
    return ", ".join(bits)
