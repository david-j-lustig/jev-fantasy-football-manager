"""Thin HTTP client for Sleeper's official API plus community stats/projections."""

from __future__ import annotations

from typing import Any

import httpx

from jev_ff._version import __version__
from jev_ff.errors import SleeperError
from jev_ff.sleeper.cache import JsonFileCache
from jev_ff.sleeper.models import (
    League,
    NFLState,
    Player,
    Projection,
    Roster,
    TrendingPlayer,
    User,
)

OFFICIAL_BASE = "https://api.sleeper.app/v1"
UNOFFICIAL_BASE = "https://api.sleeper.com"
USER_AGENT = f"jev-fantasy-football-manager/{__version__}"
PLAYERS_CACHE_NAME = "players_nfl.json"


class SleeperClient:
    """Read-only Sleeper client.

    Official endpoints need no token. Stats and projections live on
    ``api.sleeper.com`` and are community-documented, not part of the
    official public API.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        cache: JsonFileCache | None = None,
        transport: httpx.BaseTransport | None = None,
        official_base: str = OFFICIAL_BASE,
        unofficial_base: str = UNOFFICIAL_BASE,
    ) -> None:
        self.official_base = official_base.rstrip("/")
        self.unofficial_base = unofficial_base.rstrip("/")
        self.cache = cache or JsonFileCache()
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SleeperClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, url: str) -> Any:
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            raise SleeperError(f"Request failed: {url}") from exc
        if response.status_code == 404:
            raise SleeperError(f"Not found: {url}")
        if response.status_code >= 400:
            raise SleeperError(f"HTTP {response.status_code} for {url}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError as exc:
            raise SleeperError(f"Invalid JSON from {url}") from exc

    def get_state(self, sport: str = "nfl") -> NFLState:
        payload = self._get(f"{self.official_base}/state/{sport}")
        return NFLState.model_validate(payload)

    def get_user(self, username_or_id: str) -> dict[str, Any]:
        payload = self._get(f"{self.official_base}/user/{username_or_id}")
        if not isinstance(payload, dict) or not payload.get("user_id"):
            raise SleeperError(f"Unknown Sleeper user: {username_or_id}")
        return payload

    def get_league(self, league_id: str) -> League:
        payload = self._get(f"{self.official_base}/league/{league_id}")
        return League.model_validate(payload)

    def get_rosters(self, league_id: str) -> list[Roster]:
        payload = self._get(f"{self.official_base}/league/{league_id}/rosters")
        if not isinstance(payload, list):
            raise SleeperError("Unexpected rosters payload")
        return [Roster.model_validate(item) for item in payload]

    def get_users(self, league_id: str) -> list[User]:
        payload = self._get(f"{self.official_base}/league/{league_id}/users")
        if not isinstance(payload, list):
            raise SleeperError("Unexpected users payload")
        return [User.model_validate(item) for item in payload]

    def get_matchups(self, league_id: str, week: int) -> list[dict[str, Any]]:
        payload = self._get(f"{self.official_base}/league/{league_id}/matchups/{week}")
        return payload if isinstance(payload, list) else []

    def get_transactions(self, league_id: str, week: int) -> list[dict[str, Any]]:
        payload = self._get(f"{self.official_base}/league/{league_id}/transactions/{week}")
        return payload if isinstance(payload, list) else []

    def get_players(self, sport: str = "nfl", *, refresh: bool = False) -> dict[str, Player]:
        if not refresh:
            cached = self.cache.get(PLAYERS_CACHE_NAME)
            if isinstance(cached, dict):
                return _players_from_map(cached)
        payload = self._get(f"{self.official_base}/players/{sport}")
        if not isinstance(payload, dict):
            raise SleeperError("Unexpected players payload")
        self.cache.set(PLAYERS_CACHE_NAME, payload)
        return _players_from_map(payload)

    def get_trending(
        self,
        sport: str = "nfl",
        kind: str = "add",
        *,
        lookback_hours: int = 24,
        limit: int = 25,
    ) -> list[TrendingPlayer]:
        payload = self._get(
            f"{self.official_base}/players/{sport}/trending/{kind}?lookback_hours={lookback_hours}&limit={limit}"
        )
        if not isinstance(payload, list):
            return []
        trending: list[TrendingPlayer] = []
        for item in payload:
            if isinstance(item, dict) and item.get("player_id"):
                trending.append(TrendingPlayer.model_validate(item))
        return trending

    def get_projections(
        self,
        season: str | int,
        week: int | None = None,
        *,
        season_type: str = "regular",
    ) -> dict[str, Projection]:
        payload = self._get(_stats_url(self.unofficial_base, "projections", season, week, season_type))
        return _projections_from_payload(payload, week=week, season=str(season))

    def get_stats(
        self,
        season: str | int,
        week: int | None = None,
        *,
        season_type: str = "regular",
    ) -> dict[str, dict[str, Any]]:
        payload = self._get(_stats_url(self.unofficial_base, "stats", season, week, season_type))
        return _stats_from_payload(payload)

    def get_schedule(
        self,
        season: str | int,
        *,
        season_type: str = "regular",
    ) -> list[dict[str, Any]]:
        """Community schedule endpoint. Returns [] if unavailable."""
        url = f"{self.unofficial_base}/schedule/nfl/{season_type}/{season}"
        try:
            payload = self._get(url)
        except SleeperError:
            return []
        return payload if isinstance(payload, list) else []


def _stats_url(base: str, kind: str, season: str | int, week: int | None, season_type: str) -> str:
    url = f"{base}/{kind}/nfl/{season}"
    if week is not None:
        url += f"/{week}"
    return f"{url}?season_type={season_type}"


def _players_from_map(payload: dict[str, Any]) -> dict[str, Player]:
    players: dict[str, Player] = {}
    for player_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        data = dict(raw)
        data.setdefault("player_id", str(player_id))
        try:
            players[str(player_id)] = Player.model_validate(data)
        except Exception:
            continue
    return players


def _projections_from_payload(
    payload: Any,
    *,
    week: int | None,
    season: str,
) -> dict[str, Projection]:
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = list(payload.values()) if payload and not _looks_like_projection(payload) else [payload]
    else:
        return {}
    projections: dict[str, Projection] = {}
    for item in items:
        parsed = _parse_projection(item, week=week, season=season)
        if parsed is not None:
            projections[parsed.player_id] = parsed
    return projections


def _looks_like_projection(payload: dict[str, Any]) -> bool:
    return "player_id" in payload or "stats" in payload


def _parse_projection(item: Any, *, week: int | None, season: str) -> Projection | None:
    if not isinstance(item, dict):
        return None
    player_id = item.get("player_id")
    if not player_id and isinstance(item.get("player"), dict):
        player_id = item["player"].get("player_id")
    if not player_id:
        return None
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    # Some payloads put the stat line at the top level.
    if not stats:
        stats = {
            key: value
            for key, value in item.items()
            if isinstance(value, (int, float)) and key not in {"week", "count"}
        }
    opponent = item.get("opponent") or item.get("opp")
    if opponent in ("", "None"):
        opponent = None
    return Projection(
        player_id=str(player_id),
        stats={str(key): float(value) for key, value in stats.items() if isinstance(value, (int, float))},
        opponent=str(opponent) if opponent else None,
        week=item.get("week", week),
        season=str(item.get("season") or season),
        company=item.get("company"),
    )


def _stats_from_payload(payload: Any) -> dict[str, dict[str, Any]]:
    items: list[tuple[str, dict[str, Any]]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("player_id"):
                items.append((str(item["player_id"]), item))
    elif isinstance(payload, dict):
        for key, item in payload.items():
            if isinstance(item, dict):
                player_id = str(item.get("player_id") or key)
                items.append((player_id, item))
    stats_by_player: dict[str, dict[str, Any]] = {}
    for player_id, item in items:
        stats = item.get("stats") if isinstance(item.get("stats"), dict) else item
        stats_by_player[player_id] = dict(stats)
        if item.get("opponent"):
            stats_by_player[player_id]["opponent"] = item["opponent"]
    return stats_by_player
