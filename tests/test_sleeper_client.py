import httpx

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
