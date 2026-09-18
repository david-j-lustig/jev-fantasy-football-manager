"""Resolve player names and nicknames to Sleeper ids."""

from __future__ import annotations

import re
from collections.abc import Mapping

from jev_ff.errors import PlayerLookupError
from jev_ff.sleeper.models import Player

_ALIASES = {
    "cmc": "christian mccaffrey",
    "cd": "ceedee lamb",
    "cee dee": "ceedee lamb",
    "ceedee": "ceedee lamb",
    "puka": "puka nacua",
    "jt": "jonathan taylor",
    "saquon": "saquon barkley",
    "hurts": "jalen hurts",
    "mahomes": "patrick mahomes",
    "jefferson": "justin jefferson",
    "jj": "justin jefferson",
    "chase": "ja'marr chase",
    "aj brown": "aj brown",
    "kelce": "travis kelce",
    "kittle": "george kittle",
    "aemon ra": "amon-ra st. brown",
    "amon ra": "amon-ra st. brown",
    "st brown": "amon-ra st. brown",
    "nabers": "malik nabers",
    "btj": "brian thomas",
    "nico": "nico collins",
    "kyren": "kyren williams",
    "bijan": "bijan robinson",
    "breece": "breece hall",
    "achane": "devaughn achane",
    "ken walker": "kenneth walker",
    "dk": "dk metcalf",
    "aem": "amon-ra st. brown",
}


def normalize_name(value: str) -> str:
    lowered = value.casefold().strip()
    lowered = lowered.replace(".", "").replace("'", "").replace("-", " ")
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def resolve_players(queries: list[str], players: Mapping[str, Player]) -> list[Player]:
    return [resolve_player(query, players) for query in queries]


def resolve_player(query: str, players: Mapping[str, Player]) -> Player:
    raw = query.strip()
    if not raw:
        raise PlayerLookupError("Empty player name")
    if raw in players:
        return players[raw]

    needle = normalize_name(_ALIASES.get(normalize_name(raw), raw))
    exact: list[Player] = []
    last_name_hits: list[Player] = []
    contains: list[Player] = []

    for player in players.values():
        full = normalize_name(player.full_name)
        search = normalize_name(player.search_full_name or "")
        last = normalize_name(player.last_name or player.search_last_name or "")
        team_def = normalize_name(f"{player.player_id} def") if player.position == "DEF" else ""
        if needle in {full, search, team_def}:
            exact.append(player)
        elif last and needle == last:
            last_name_hits.append(player)
        elif needle and (needle in full or (search and needle in search)):
            contains.append(player)

    for group in (exact, last_name_hits, contains):
        unique = _unique(group)
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            names = ", ".join(sorted(p.full_name for p in unique[:8]))
            raise PlayerLookupError(f"Ambiguous player '{query}': {names}")

    raise PlayerLookupError(f"Unknown player: {query}")


def _unique(players: list[Player]) -> list[Player]:
    seen: dict[str, Player] = {}
    for player in players:
        seen[player.player_id] = player
    return list(seen.values())
