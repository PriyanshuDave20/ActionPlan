from pydantic import BaseModel, Field

from app.models.evidence import Evidence


class OptimizationResult(BaseModel):
    summary: str
    critical_path: list[str] = Field(default_factory=list)
    critical_path_effort: int = 0
    parallel_chains: list[list[str]] = Field(default_factory=list)
    days_until_deadline: int | None = None
    deadline_feasible: bool | None = None
    deadline_notes: str | None = None
    notes: list[str] = Field(default_factory=list)


class TargetedEvidence(BaseModel):
    requirement_id: str
    query: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)