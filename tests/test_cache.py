import json
import time

from jev_ff.sleeper.cache import JsonFileCache


def test_round_trip(tmp_path) -> None:
    cache = JsonFileCache(cache_dir=tmp_path, ttl_seconds=60)
    cache.set("players_nfl.json", {"1": {"player_id": "1"}})
    assert cache.get("players_nfl.json") == {"1": {"player_id": "1"}}


def test_expired(tmp_path) -> None:
    cache = JsonFileCache(cache_dir=tmp_path, ttl_seconds=1)
    path = tmp_path / "players_nfl.json"
    path.write_text(json.dumps({"saved_at": time.time() - 10, "data": {"stale": True}}))
    assert cache.get("players_nfl.json") is None
