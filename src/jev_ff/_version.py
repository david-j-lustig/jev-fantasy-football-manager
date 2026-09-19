"""Package version from installed dist metadata (pyproject.toml is the source of truth)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("jev-fantasy-football-manager")
except PackageNotFoundError:  # source tree without an install
    __version__ = "0.0.0"
