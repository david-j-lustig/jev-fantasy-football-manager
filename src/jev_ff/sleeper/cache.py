"""On-disk cache for the bulky Sleeper NFL player map."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_TTL_SECONDS = 24 * 60 * 60


def default_cache_dir() -> Path:
    override = os.environ.get("JEV_FF_CACHE_DIR")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "jev_ff"


class JsonFileCache:
    def __init__(self, cache_dir: Path | None = None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.cache_dir = cache_dir or default_cache_dir()
        self.ttl_seconds = ttl_seconds

    def _path(self, name: str) -> Path:
        return self.cache_dir / name

    def get(self, name: str) -> Any | None:
        path = self._path(name)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        saved_at = payload.get("saved_at")
        if not isinstance(saved_at, (int, float)):
            return None
        if time.time() - saved_at > self.ttl_seconds:
            return None
        return payload.get("data")

    def set(self, name: str, data: Any) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"saved_at": time.time(), "data": data}))
        tmp.replace(path)
