from typing import Literal

from pydantic import BaseModel, Field


class CandidateTask(BaseModel):
    task_id: str
    title: str | None = None
    description: str
    completion_criteria: list[str] = Field(default_factory=list)
    deliverable: str | None = None
    deliverable_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    requirement_id: str | None = None
    procedure_id: str | None = None
    effort: Literal["small", "medium", "large", "high"] = "small"
    priority: Literal["low", "medium", "high"] | None = None
    phase: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)


class CandidatePlan(BaseModel):
    rationale: str
    assumptions: list[str] = Field(default_factory=list)
    tasks: list[CandidateTask] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    code: str
    message: str
    task_id: str | None = None


class PlanValidationResult(BaseModel):
    valid: bool = True
    summary: str = "plan is consistent"
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    invalid_dependencies: list[str] = Field(default_factory=list)
    missing_approvals: list[str] = Field(default_factory=list)
    sequencing_violations: list[str] = Field(default_factory=list)
    uncovered_requirements: list[str] = Field(default_factory=list)
    uncovered_deliverables: list[str] = Field(default_factory=list)
    revision_count: int = 0