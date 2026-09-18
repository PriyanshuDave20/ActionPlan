from typing import Any, TypedDict

from app.models.evidence import Evidence
from app.models.optimization import OptimizationResult, TargetedEvidence
from app.models.plan import CandidatePlan, PlanValidationResult
from app.models.procedure import Procedure
from app.models.requirement import Requirement
from app.models.task import Task
from app.models.work_request import WorkRequest, WorkRequestInput
from app.models.workflow import Blocker, Recommendation


class AgentState(TypedDict, total=False):
    workflow_id: str
    original_goal: str
    work_request_input: WorkRequestInput
    work_request: WorkRequest
    objective_analysis: dict[str, Any]
    goal_analysis: dict[str, Any] | None
    planner_steps: list[str]
    procedure_analysis: dict[str, Any]
    procedures: list[Procedure]
    requirements: list[Requirement]
    function_definitions: dict[str, Any]
    candidate_plan: CandidatePlan
    plan_validation: PlanValidationResult
    plan_revision_count: int
    optimization: OptimizationResult
    tasks: list[Task]
    completed_tasks: list[str]
    blocked_tasks: list[str]
    current_task: str | None
    current_state: dict[str, Any]
    retrieved_documents: list[Evidence]
    targeted_evidence: list[TargetedEvidence]
    targeted_by_requirement: dict[str, list[str]]
    detected_blockers: list[Blocker]
    recommendation: Recommendation | None
    memory_context: list[str]
    execution_metadata: dict[str, object]
    incoming_completed_task_ids: list[str]