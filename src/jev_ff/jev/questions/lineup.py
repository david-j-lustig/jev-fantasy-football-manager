"""Atomic lineup questions for TypeSafe Jev."""

from __future__ import annotations

from typing import Any


def inactive_question(player_name: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": (
            f"Given the injury status, practice reports, and headlines for {player_name}, "
            "is this player likely to be inactive or clearly limited this NFL week?"
        ),
        "criteria": {
            "true": ("Ruled out, expected to sit, or so limited that a typical fantasy start is a bad idea."),
            "false": ("Expected to play a normal or near-normal snap share, or the notes do not justify sitting."),
        },
    }


def discount_question(player_name: str) -> dict[str, Any]:
    return {
        "type": "score",
        "instructions": (
            f"How much should we discount {player_name}'s projection this week given news and injury notes?"
        ),
        "criteria": [
            "No discount — news does not change the projection.",
            "Slight discount — minor limitation, weather, or role concern.",
            "Major discount — clearly reduced snaps or a tough situation the projection misses.",
            "Sit — should not be started if any alternative exists.",
        ],
    }


def start_sit_question(slot: str, names: dict[str, str]) -> dict[str, Any]:
    criteria = {key: f"Start {name} in {slot}." for key, name in names.items()}
    criteria["other"] = "None of these players is a clear start, or information is insufficient."
    return {
        "type": "choice",
        "instructions": (
            f"Who should start in the {slot} slot this week? Prefer the player more likely to outscore "
            "the others after accounting for injury, news, and matchup — not just the raw projection."
        ),
        "criteria": criteria,
    }
