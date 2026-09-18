from pydantic import BaseModel, Field

from app.models.procedure import Procedure


class ObjectiveAnalysis(BaseModel):
    objective: str
    current_situation: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    decision_makers: list[str] = Field(default_factory=list)
    external_dependencies: list[str] = Field(default_factory=list)
    timeline_flags: list[str] = Field(default_factory=list)
    priority_flags: list[str] = Field(default_factory=list)
    notes: str | None = None


class ProcedureExtraction(BaseModel):
    summary: str
    procedures: list[Procedure] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)