"""Waiver-wire questions for TypeSafe Jev."""

from __future__ import annotations

from typing import Any


def add_worth_it_question(add_name: str, drop_name: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": (
            f"Is adding {add_name} and dropping {drop_name} a good fantasy waiver move this week, "
            "given positional need, news, and rest-of-season outlook?"
        ),
        "criteria": {
            "true": "The add is clearly more valuable than the drop for this roster.",
            "false": "The add is a luxury, a stash of similar value, or worse than keeping the drop.",
        },
    }


def faab_question(add_name: str) -> dict[str, Any]:
    return {
        "type": "score",
        "instructions": f"How aggressively should this team bid FAAB for {add_name}?",
        "criteria": [
            "Ignore / $0 — not worth a claim.",
            "Streaming / cheap — small bid, replaceable.",
            "Solid roster upgrade — medium FAAB.",
            "Must-add — spend heavily; this player should not hit waivers.",
        ],
    }


def best_drop_question(names: dict[str, str]) -> dict[str, Any]:
    criteria = {key: f"Drop {name}." for key, name in names.items()}
    criteria["other"] = "None of these is a good drop, or an IR move is better."
    return {
        "type": "choice",
        "instructions": "If we must drop someone to make room, who is the least valuable keep?",
        "criteria": criteria,
    }
