"""Sleeper and NFL domain models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Player(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: str
    first_name: str = ""
    last_name: str = ""
    team: str | None = None
    position: str | None = None
    fantasy_positions: list[str] = Field(default_factory=list)
    injury_status: str | None = None
    injury_notes: str | None = None
    practice_participation: str | None = None
    status: str | None = None
    search_full_name: str | None = None
    search_first_name: str | None = None
    search_last_name: str | None = None
    number: int | str | None = None
    years_exp: int | None = None

    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        if name:
            return name
        if self.player_id and self.position == "DEF":
            return f"{self.player_id} DEF"
        return self.player_id

    @property
    def positions(self) -> list[str]:
        if self.fantasy_positions:
            return self.fantasy_positions
        if self.position:
            return [self.position]
        return []


class League(BaseModel):
    model_config = ConfigDict(extra="ignore")

    league_id: str
    name: str = ""
    season: str = ""
    scoring_settings: dict[str, float] = Field(default_factory=dict)
    roster_positions: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    sport: str = "nfl"
    season_type: str = "regular"
    total_rosters: int | None = None


class Roster(BaseModel):
    model_config = ConfigDict(extra="ignore")

    roster_id: int
    owner_id: str | None = None
    players: list[str] = Field(default_factory=list)
    starters: list[str] = Field(default_factory=list)
    reserve: list[str] | None = None
    taxi: list[str] | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("players", "starters", mode="before")
    @classmethod
    def _none_to_list(cls, value: Any) -> list[str]:
        if not value:
            return []
        return [str(item) for item in value if item not in (None, "")]


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: str
    display_name: str = ""
    username: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def team_name(self) -> str:
        meta_name = self.metadata.get("team_name") if self.metadata else None
        if isinstance(meta_name, str) and meta_name.strip():
            return meta_name
        return self.display_name or self.user_id


class NFLState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    week: int = 1
    display_week: int | None = None
    season: str = ""
    season_type: str = "regular"
    league_season: str | None = None
    season_start_date: str | None = None

    @property
    def current_week(self) -> int:
        return int(self.display_week or self.week or 1)


class Projection(BaseModel):
    """Weekly or season projection for one player."""

    model_config = ConfigDict(extra="ignore")

    player_id: str
    stats: dict[str, float] = Field(default_factory=dict)
    opponent: str | None = None
    week: int | None = None
    season: str | None = None
    company: str | None = None


class TrendingPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: str
    count: int = 0
