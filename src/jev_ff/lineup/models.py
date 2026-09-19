from __future__ import annotations

from pydantic import BaseModel, Field

from jev_ff.sleeper.models import Player


class LineupAssignment(BaseModel):
    slot: str
    player: Player | None = None
    projected_points: float = 0.0
    reason: str = ""
    needs_review: bool = False


class LineupReport(BaseModel):
    week: int
    season: str
    roster_id: int
    starters: list[LineupAssignment] = Field(default_factory=list)
    bench: list[LineupAssignment] = Field(default_factory=list)
    projected_total: float = 0.0
    current_total: float = 0.0
    jev_enabled: bool = False
    notes: list[str] = Field(default_factory=list)

    @property
    def delta(self) -> float:
        return round(self.projected_total - self.current_total, 4)
