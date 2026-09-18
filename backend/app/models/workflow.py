from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.evidence import Evidence
from app.models.optimization import OptimizationResult, TargetedEvidence
from app.models.plan import CandidatePlan, PlanValidationResult
from app.models.procedure import Procedure
from app.models.requirement import Requirement
from app.models.task import Task
from app.models.work_request import WorkRequest


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Blocker(BaseModel):
    task_id: str = ""
    type: str = "dependency"
    message: str = ""


class Recommendation(BaseModel):
    action: str
    reason: str
    priority: str = "medium"
    affected_task: str | None = None
    requirement_id: str | None = None
    role: str | None = None
    blocked_by: str | None = None
    evidence: list[str] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    deadline_pressure: str = "none"


class ContinueRequest(BaseModel):
    completed_task_ids: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    filename: str
    chunks: int


class WorkflowSummary(BaseModel):
    workflow_id: str
    goal: str
    updated_at: datetime
    deadline: date | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    total_tasks: int = 0
    completed_tasks: int = 0
    blocker_count: int = 0
    recommendation_action: str | None = None


class WorkflowState(BaseModel):
    workflow_id: str
    original_goal: str
    work_request: WorkRequest | None = None
    objective_analysis: dict[str, Any] | None = None
    goal_analysis: dict[str, Any] | None = None
    planner_steps: list[str] = Field(default_factory=list)
    procedure_analysis: dict[str, Any] | None = None
    procedures: list[Procedure] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    candidate_plan: CandidatePlan | None = None
    plan_validation: PlanValidationResult | None = None
    plan_revision_count: int = 0
    optimization: OptimizationResult | None = None
    tasks: list[Task] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)
    blocked_tasks: list[str] = Field(default_factory=list)
    current_task: str | None = None
    current_state: dict[str, Any] = Field(default_factory=dict)
    function_definitions: dict[str, Any] = Field(default_factory=dict)
    retrieved_documents: list[Evidence] = Field(default_factory=list)
    targeted_evidence: list[TargetedEvidence] = Field(default_factory=list)
    targeted_by_requirement: dict[str, list[str]] = Field(default_factory=dict)
    detected_blockers: list[Blocker] = Field(default_factory=list)
    recommendation: Recommendation | None = None
    memory_context: list[str] = Field(default_factory=list)
    execution_metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)