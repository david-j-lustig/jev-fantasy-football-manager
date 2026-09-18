from __future__ import annotations

from jev_ff.jev.client import JevResult
from jev_ff.sleeper.models import League, Player, Roster, User


def make_player(
    player_id: str,
    name: str,
    position: str,
    *,
    team: str | None = "SF",
    injury_status: str | None = None,
    injury_notes: str | None = None,
) -> Player:
    first, _, last = name.partition(" ")
    return Player(
        player_id=player_id,
        first_name=first,
        last_name=last,
        team=team,
        position=position,
        fantasy_positions=[position],
        injury_status=injury_status,
        injury_notes=injury_notes,
        status="Active",
        search_full_name=name.replace(" ", "").lower(),
        search_first_name=first.lower(),
        search_last_name=last.lower(),
    )


def sample_league(**kwargs) -> League:
    data = {
        "league_id": "L1",
        "name": "Test League",
        "season": "2025",
        "scoring_settings": {
            "pass_yd": 0.04,
            "pass_td": 4,
            "rush_yd": 0.1,
            "rush_td": 6,
            "rec": 0.5,
            "rec_yd": 0.1,
            "rec_td": 6,
            "fum_lost": -2,
        },
        "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN", "BN"],
    }
    data.update(kwargs)
    return League.model_validate(data)


def sample_roster(
    roster_id: int = 1,
    players: list[str] | None = None,
    starters: list[str] | None = None,
) -> Roster:
    players = players or []
    return Roster(roster_id=roster_id, owner_id=f"U{roster_id}", players=players, starters=starters or [])


def sample_user(user_id: str = "U1", name: str = "Tester") -> User:
    return User(user_id=user_id, display_name=name, username=name.lower())


class ScriptedJev:
    def __init__(self, result: JevResult | None = None, **overrides) -> None:
        self.result = result
        self.overrides = overrides
        self.calls: list[tuple[object, dict]] = []

    def system_one(self, state, questions) -> JevResult:
        self.calls.append((state, questions))
        if self.result is not None:
            return self.result
        from jev_ff.jev.client import NullJevEvaluator

        base = NullJevEvaluator().system_one(state, questions)
        for key, value in self.overrides.items():
            if key in base.nouls and hasattr(value, "noul"):
                base.nouls[key] = value
            elif key in base.choices and hasattr(value, "choice"):
                base.choices[key] = value
            elif key in base.scores and hasattr(value, "score"):
                base.scores[key] = value
        return base
