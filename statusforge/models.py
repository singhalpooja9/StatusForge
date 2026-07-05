"""Data models for StatusForge.

`TeamSignals` is the typed, numeric state extracted from a team's raw status — the
ONLY thing the rule engine reads. `Verdict` is what the engine returns. Keeping the
engine's input and output as strict Pydantic models is what guarantees the LLM has
no numeric path to the Red/Amber/Green decision: the model may *fill* TeamSignals
during extraction, but a human can inspect/override every number, and the color is
computed from those numbers by deterministic code — never emitted by the LLM.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Color = Literal["Green", "Amber", "Red"]


class TeamSignals(BaseModel):
    """The numeric health signals for one workstream/team.

    These are the inputs to the deterministic rule engine. Every field is a plain
    number or count so the RAG color is a pure function of this object.
    """

    team: str
    critical_path_slip_days: int = Field(
        0, ge=0, description="Days the team's deliverable has slipped on the critical path")
    open_p1s: int = Field(0, ge=0, description="Open Sev-1 / P1 issues")
    blocked_dependencies: int = Field(0, ge=0, description="Dependencies currently blocked")
    ownerless_blocked_deps: int = Field(
        0, ge=0, description="Blocked dependencies with no named owner (worse than owned)")
    scope_delta_pct: float = Field(
        0.0, description="Scope change since baseline, percent (+ added / - cut)")
    milestones_total: int = Field(0, ge=0)
    milestones_hit: int = Field(0, ge=0)

    def model_post_init(self, __ctx) -> None:  # noqa: D401
        # Guard the one cross-field invariant the engine relies on.
        if self.milestones_hit > self.milestones_total:
            raise ValueError(
                f"{self.team}: milestones_hit ({self.milestones_hit}) > "
                f"milestones_total ({self.milestones_total})")


class Verdict(BaseModel):
    """The engine's output for one team: a color, the reasons that fired, and the
    narrative (added later by the LLM, which may NOT change the color)."""

    team: str
    color: Color
    reasons: list[str] = Field(default_factory=list, description="Which rules fired, in plain English")
    signals: TeamSignals
    narrative: str = ""

    @property
    def rank(self) -> int:
        """Sort order for a rollup: Red first."""
        return {"Red": 0, "Amber": 1, "Green": 2}[self.color]


class ProgramRollup(BaseModel):
    """Program-level rollup across teams. The program color is the WORST team color
    (a program is only as healthy as its reddest workstream)."""

    program_color: Color
    teams: list[Verdict]
    summary: str = ""
