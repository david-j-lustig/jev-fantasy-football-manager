"""Roster slot eligibility for Sleeper lineup positions."""

from __future__ import annotations

from jev_ff.sleeper.models import Player

BENCH_SLOTS = {"BN", "IR", "TAXI", "RESERVE"}

SLOT_ELIGIBILITY: dict[str, set[str]] = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "DEF": {"DEF"},
    "DL": {"DL", "DE", "DT"},
    "LB": {"LB", "ILB", "OLB"},
    "DB": {"DB", "CB", "S", "FS", "SS"},
    "IDP": {"DL", "DE", "DT", "LB", "ILB", "OLB", "DB", "CB", "S", "FS", "SS", "IDP"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "Q/W/R/T": {"QB", "RB", "WR", "TE"},
    "W/R/T": {"RB", "WR", "TE"},
    "W/T": {"WR", "TE"},
    "W/R": {"RB", "WR"},
    "FLEX_IDP": {"DL", "DE", "DT", "LB", "ILB", "OLB", "DB", "CB", "S", "FS", "SS", "IDP"},
}

# Assign scarce, position-specific slots before FLEX so greedy/backtracking
# does not burn a RB on FLEX while leaving the RB slot empty.
SLOT_PRIORITY = {
    "K": 0,
    "DEF": 0,
    "QB": 1,
    "TE": 2,
    "RB": 3,
    "WR": 3,
    "DL": 3,
    "LB": 3,
    "DB": 3,
    "W/T": 4,
    "W/R": 4,
    "REC_FLEX": 4,
    "WRRB_FLEX": 4,
    "FLEX": 5,
    "W/R/T": 5,
    "IDP": 5,
    "FLEX_IDP": 6,
    "SUPER_FLEX": 7,
    "Q/W/R/T": 7,
}


def starter_slots(roster_positions: list[str]) -> list[str]:
    return [slot for slot in roster_positions if slot not in BENCH_SLOTS]


def eligible_positions(slot: str) -> set[str]:
    return SLOT_ELIGIBILITY.get(slot, {slot})


def player_can_fill(player: Player, slot: str) -> bool:
    return bool(set(player.positions) & eligible_positions(slot))


def slot_sort_key(index_and_slot: tuple[int, str]) -> tuple[int, int]:
    index, slot = index_and_slot
    return (SLOT_PRIORITY.get(slot, 10), index)
