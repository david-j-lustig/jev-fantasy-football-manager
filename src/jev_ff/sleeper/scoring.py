"""Apply a Sleeper league's scoring_settings to a raw stat/projection line."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Keys that appear in scoring_settings but are not per-play stat lines.
_SKIP_KEYS = {
    "pts_std",
    "pts_half_ppr",
    "pts_ppr",
    "pts_idp",
}


def coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def league_points(
    stats: Mapping[str, Any] | None,
    scoring_settings: Mapping[str, Any] | None,
) -> float:
    """Score a stat line with *this league's* settings.

    Never use Sleeper's pre-baked ``pts_ppr`` / ``pts_std`` fields. Those ignore
    TE premium, 6-point passing TDs, custom bonuses, and IDP.
    """
    if not stats or not scoring_settings:
        return 0.0
    total = 0.0
    for key, weight in scoring_settings.items():
        if key in _SKIP_KEYS:
            continue
        multiplier = coerce_float(weight)
        amount = coerce_float(stats.get(key))
        if multiplier is None or amount is None:
            continue
        total += amount * multiplier
    return round(total, 4)
