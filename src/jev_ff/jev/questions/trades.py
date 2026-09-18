"""Trade-evaluation questions for TypeSafe Jev."""

from __future__ import annotations

from typing import Any


def fairness_question() -> dict[str, Any]:
    return {
        "type": "score",
        "instructions": (
            "How fair is this trade for the proposing roster, given rest-of-season value, "
            "positional need, injuries, and remaining schedule? Do not invent player values; "
            "use the provided point totals and notes."
        ),
        "criteria": [
            "Bad trade — a clear loss for this roster.",
            "Slight loss — acceptable only with a specific need.",
            "Even — fair value both ways.",
            "Slight win — modest upgrade for this roster.",
            "Strong steal — the other side should not accept.",
        ],
    }


def should_accept_question() -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": "Should this roster accept the trade as proposed?",
        "criteria": {
            "true": "Accept. The roster is better or clearly not worse after positional fit.",
            "false": "Decline. Value or fit is worse for this roster.",
        },
    }


def opponent_accept_question() -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": "Would a typical opponent who owns the incoming players accept this trade?",
        "criteria": {
            "true": "Yes, a reasonable manager would accept.",
            "false": "No, it looks lopsided against them or fills no need.",
        },
    }
