from __future__ import annotations

from pydantic import BaseModel, Field

from jev_ff.sleeper.models import Player


class TradeSide(BaseModel):
    players: list[Player] = Field(default_factory=list)
    week_points: float = 0.0
    ros_points: float = 0.0


class TradeReport(BaseModel):
    week: int
    season: str
    roster_id: int
    opponent_roster_id: int | None = None
    give: TradeSide
    get: TradeSide
    ros_delta: float = 0.0
    week_delta: float = 0.0
    fairness_label: str = ""
    fairness_score: float | None = None
    should_accept: float | None = None
    opponent_would_accept: float | None = None
    recommendation: str = ""
    jev_enabled: bool = False
    notes: list[str] = Field(default_factory=list)
