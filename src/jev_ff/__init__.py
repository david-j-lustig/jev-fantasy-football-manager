"""JEV Fantasy Football Manager — recommend Sleeper lineups, waivers, and trades."""

from jev_ff._version import __version__
from jev_ff.errors import ConfigError, JevFFError, PlayerLookupError, SleeperError
from jev_ff.manager import FantasyManager
from jev_ff.models import LineupReport, TradeReport, WaiverReport

__all__ = [
    "ConfigError",
    "FantasyManager",
    "JevFFError",
    "LineupReport",
    "PlayerLookupError",
    "SleeperError",
    "TradeReport",
    "WaiverReport",
    "__version__",
]
