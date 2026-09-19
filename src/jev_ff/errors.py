"""Shared exceptions."""


class JevFFError(Exception):
    """Base error for the package."""


class SleeperError(JevFFError):
    """Sleeper HTTP or payload error."""


class ConfigError(JevFFError):
    """Missing or invalid configuration."""


class PlayerLookupError(JevFFError):
    """Could not resolve a player name or id."""


class JevError(JevFFError):
    """TypeSafe / Jev request failed."""
