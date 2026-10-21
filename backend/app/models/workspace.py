from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.task import Task
from app.models.workflow import Recommendation


class TaskPatch(BaseModel):
    description: str | None = Field(default=None, min_length=1)
    dependencies: list[str] | None = None
    acceptance_criteria: list[str] | None = None
    version: int = Field(ge=1)


class TaskTransition(BaseModel):
    status: Literal["pending", "ready", "in_progress", "completed", "blocked", "cancelled"]
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)


class WorkflowUpdateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    version: int = Field(ge=1)
    apply_proposed_changes: bool = False


class PlanRevisionRequest(BaseModel):
    tasks: list[Task]
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)


class RecommendationDecision(BaseModel):
    decision: Literal["accepted", "rejected", "revision_requested"]
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)


class WorkflowEvent(BaseModel):
    event_id: str
    workflow_id: str
    event_type: str
    occurred_at: datetime
    entity_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    actor: str = "user"
    version: int | None = None


class WorkflowEvidence(BaseModel):
    content: str
    source: str = ""
    page: int | None = None
    document_type: str = "unknown"
    provenance: Literal["organizational", "user_provided", "inference", "assumption"] = "organizational"


class WorkspaceView(BaseModel):
    version: int
    tasks: list[Task]
    recommendation: Recommendation | None = None
