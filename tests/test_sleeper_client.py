import httpx

from jev_ff.jev.client import NullJevEvaluator
from jev_ff.manager import FantasyManager
from jev_ff.sleeper.cache import JsonFileCache
from jev_ff.sleeper.client import SleeperClient


def test_get_league_projections_and_cached_players(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/state/nfl"):
            return httpx.Response(200, json={"week": 3, "display_week": 3, "season": "2025", "season_type": "regular"})
        if "/league/L1/rosters" in url:
            return httpx.Response(200, json=[{"roster_id": 1, "owner_id": "U1", "players": ["1"], "starters": ["1"]}])
        if url.endswith("/league/L1"):
            return httpx.Response(
                200,
                json={
                    "league_id": "L1",
                    "name": "Demo",
                    "season": "2025",
                    "scoring_settings": {"rec": 0.5, "rec_yd": 0.1},
                    "roster_positions": ["QB", "BN"],
                },
            )
        if "/projections/nfl/2025/3" in url:
            return httpx.Response(
                200,
                json=[{"player_id": "1", "stats": {"rec": 5, "rec_yd": 60}, "opponent": "DAL"}],
            )
        if url.endswith("/players/nfl"):
            return httpx.Response(
                200,
                json={
                    "1": {
                        "player_id": "1",
                        "first_name": "Puka",
                        "last_name": "Nacua",
                        "position": "WR",
                        "team": "LAR",
                    }
                },
            )
        return httpx.Response(404, json={"error": url})

    client = SleeperClient(
        transport=httpx.MockTransport(handler),
        cache=JsonFileCache(cache_dir=tmp_path, ttl_seconds=60),
    )
    league = client.get_league("L1")
    assert league.scoring_settings["rec"] == 0.5
    projections = client.get_projections("2025", 3)
    assert projections["1"].opponent == "DAL"
    assert projections["1"].stats["rec"] == 5
    players = client.get_players()
    assert players["1"].full_name == "Puka Nacua"
    cached = client.get_players()
    assert cached["1"].player_id == "1"
    client.close()


def test_corrupt_player_cache_refetches(tmp_path) -> None:
    cache = JsonFileCache(cache_dir=tmp_path, ttl_seconds=60)
    cache.set("players_nfl.json", {"1": "not-a-player"})
    fetches = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/players/nfl"):
            fetches["count"] += 1
            return httpx.Response(
                200,
                json={
                    "1": {
                        "player_id": "1",
                        "first_name": "Puka",
                        "last_name": "Nacua",
                        "position": "WR",
                    }
                },
            )
        return httpx.Response(404, json={"error": str(request.url)})

    client = SleeperClient(transport=httpx.MockTransport(handler), cache=cache)
    players = client.get_players()
    assert players["1"].full_name == "Puka Nacua"
    assert fetches["count"] == 1
    client.close()


def test_manager_closes_owned_sleeper_client() -> None:
    with FantasyManager("L1", roster_id=1, jev=NullJevEvaluator()) as manager:
        client = manager.sleeper._client
    assert client.is_closed


def test_manager_does_not_close_injected_sleeper(tmp_path) -> None:
    injected = SleeperClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
        cache=JsonFileCache(cache_dir=tmp_path, ttl_seconds=60),
    )
    with FantasyManager("L1", roster_id=1, sleeper=injected, jev=NullJevEvaluator()):
        pass
    assert not injected._client.is_closed
    injected.close()
