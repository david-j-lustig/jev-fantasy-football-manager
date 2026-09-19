from __future__ import annotations

from pydantic import BaseModel, Field

from jev_ff.sleeper.models import Player


class WaiverAdd(BaseModel):
    player: Player
    week_points: float
    ros_points: float
    vor_week: float
    vor_ros: float
    score: float
    trending_adds: int = 0
    drop: Player | None = None
    faab_label: str = ""
    faab_score: float | None = None
    worth_it: float | None = None
    reason: str = ""


class WaiverReport(BaseModel):
    week: int
    season: str
    roster_id: int
    adds: list[WaiverAdd] = Field(default_factory=list)
    jev_enabled: bool = False
    notes: list[str] = Field(default_factory=list)
    suggested_drop: Player | None = None
