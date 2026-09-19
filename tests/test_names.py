import pytest

from jev_ff.errors import PlayerLookupError
from jev_ff.names import resolve_player
from tests.factories import make_player


def _players():
    return {
        "4046": make_player("4046", "Christian McCaffrey", "RB"),
        "4984": make_player("4984", "Puka Nacua", "WR", team="LAR"),
        "1": make_player("1", "Justin Jefferson", "WR", team="MIN"),
        "2": make_player("2", "Justin Fields", "QB", team="NYJ"),
        "9758": make_player("9758", "De'Von Achane", "RB", team="MIA"),
        "SF": make_player("SF", "49ers", "DEF", team="SF"),
    }


@pytest.mark.parametrize(
    ("query", "player_id"),
    [
        ("4046", "4046"),
        ("CMC", "4046"),
        ("puka nacua", "4984"),
        ("achane", "9758"),
    ],
)
def test_resolve_player(query: str, player_id: str) -> None:
    assert resolve_player(query, _players()).player_id == player_id


def test_ambiguous_name_raises() -> None:
    with pytest.raises(PlayerLookupError, match="Ambiguous"):
        resolve_player("Justin", _players())


def test_unknown_name_raises() -> None:
    with pytest.raises(PlayerLookupError, match="Unknown"):
        resolve_player("nobody", _players())
