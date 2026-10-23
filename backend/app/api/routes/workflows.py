from fastapi import APIRouter, Depends, HTTPException

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service
from app.api.dependencies import get_workspace
from app.models.workflow import WorkflowState, WorkflowSummary
from app.models.workspace import PlanRevisionRequest, RecommendationDecision, TaskPatch, TaskTransition, WorkflowEvent, WorkflowEvidence, WorkflowUpdateRequest
from app.workspace import Conflict, NotFound, WorkspaceError, WorkspaceStore, transition_task

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _workspace_workflow(workflow_id: str, service: AgentService, workspace: WorkspaceStore) -> WorkflowState:
    try:
        return workspace.get(workflow_id)
    except NotFound:
        legacy = service.get_workflow(workflow_id)
        if legacy is None:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
        return workspace.ensure(legacy)


def _raise(error: WorkspaceError) -> None:
    raise HTTPException(status_code=error.status_code, detail=str(error))


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(
    service: AgentService = Depends(get_agent_service),
) -> list[WorkflowSummary]:
    return service.list_workflows()


@router.get("/{workflow_id}", response_model=WorkflowState)
def get_workflow(
    workflow_id: str,
    service: AgentService = Depends(get_agent_service),
    workspace: WorkspaceStore = Depends(get_workspace),
) -> WorkflowState:
    return _workspace_workflow(workflow_id, service, workspace)


@router.post("/{workflow_id}/refresh", response_model=WorkflowState)
def refresh_workflow(
    workflow_id: str,
    service: AgentService = Depends(get_agent_service),
    workspace: WorkspaceStore = Depends(get_workspace),
) -> WorkflowState:
    # Read the freshest state from the durable store (DynamoDB). The local
    # SQLite workspace can hold a stale pre-worker copy (no work_request,
    # no documents, execution_state=QUEUED) that would produce an empty plan
    # and lose the ingested-document references.
    workflow = service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    rebuilt = service.rebuild_workflow(workflow)
    # Sync the fresh source into SQLite so the optimistic-version check in
    # save() passes even if SQLite held a different version.
    workspace.ensure(workflow)
    try: return workspace.save(rebuilt, workflow.version, "assessment_completed", actor="system")
    except WorkspaceError as error: _raise(error)


@router.patch("/{workflow_id}/tasks/{task_id}", response_model=WorkflowState)
def patch_task(workflow_id: str, task_id: str, payload: TaskPatch, service: AgentService = Depends(get_agent_service), workspace: WorkspaceStore = Depends(get_workspace)) -> WorkflowState:
    workflow = _workspace_workflow(workflow_id, service, workspace)
    task = next((item for item in workflow.tasks if item.id == task_id), None)
    if task is None: raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    for field, value in payload.model_dump(exclude_none=True, exclude={"version"}).items(): setattr(task, field, value)
    try: return workspace.save(workflow, payload.version, "task_edited", task_id, {"fields": list(payload.model_dump(exclude_none=True, exclude={"version"}))})
    except WorkspaceError as error: _raise(error)


@router.post("/{workflow_id}/tasks/{task_id}/transition", response_model=WorkflowState)
def transition(workflow_id: str, task_id: str, payload: TaskTransition, service: AgentService = Depends(get_agent_service), workspace: WorkspaceStore = Depends(get_workspace)) -> WorkflowState:
    workflow = _workspace_workflow(workflow_id, service, workspace)
    try:
        transition_task(workflow, task_id, payload.status)
        return workspace.save(workflow, payload.version, "task_status_changed", task_id, {"status": payload.status, "reason": payload.reason or ""})
    except WorkspaceError as error: _raise(error)


@router.get("/{workflow_id}/events", response_model=list[WorkflowEvent])
def events(workflow_id: str, service: AgentService = Depends(get_agent_service), workspace: WorkspaceStore = Depends(get_workspace)) -> list[WorkflowEvent]:
    _workspace_workflow(workflow_id, service, workspace)
    return workspace.events(workflow_id)


@router.get("/{workflow_id}/evidence", response_model=list[WorkflowEvidence])
def evidence(workflow_id: str, service: AgentService = Depends(get_agent_service), workspace: WorkspaceStore = Depends(get_workspace)) -> list[WorkflowEvidence]:
    workflow = _workspace_workflow(workflow_id, service, workspace)
    return [WorkflowEvidence(content=item.content, source=item.source, page=item.page, document_type=item.document_type, provenance="organizational") for item in workflow.retrieved_documents]


@router.post("/{workflow_id}/plan/revisions", response_model=WorkflowState)
def revise_plan(workflow_id: str, payload: PlanRevisionRequest, service: AgentService = Depends(get_agent_service), workspace: WorkspaceStore = Depends(get_workspace)) -> WorkflowState:
    workflow = _workspace_workflow(workflow_id, service, workspace)
    try: return workspace.revise(workflow, payload.version, payload.tasks, payload.reason)
    except WorkspaceError as error: _raise(error)


@router.post("/{workflow_id}/updates", response_model=WorkflowState)
def update(workflow_id: str, payload: WorkflowUpdateRequest, service: AgentService = Depends(get_agent_service), workspace: WorkspaceStore = Depends(get_workspace)) -> WorkflowState:
    workflow = _workspace_workflow(workflow_id, service, workspace)
    workflow.execution_metadata.setdefault("user_updates", []).append({"text": payload.text, "at": "user-provided"})
    workflow.last_assessed_at = workflow.updated_at
    try: return workspace.save(workflow, payload.version, "user_information_supplied", details={"text": payload.text}, actor="user")
    except WorkspaceError as error: _raise(error)


@router.post("/{workflow_id}/recommendations/{recommendation_id}/decision", response_model=WorkflowState)
def recommendation_decision(workflow_id: str, recommendation_id: str, payload: RecommendationDecision, service: AgentService = Depends(get_agent_service), workspace: WorkspaceStore = Depends(get_workspace)) -> WorkflowState:
    workflow = _workspace_workflow(workflow_id, service, workspace)
    recommendation = workflow.recommendation
    if recommendation is None or recommendation.recommendation_id != recommendation_id: raise HTTPException(status_code=404, detail="Recommendation not found.")
    if recommendation.status == "stale" or workflow.version != payload.version: raise HTTPException(status_code=409, detail="Recommendation is stale. Review the current workflow first.")
    recommendation.status = payload.decision; recommendation.decision_reason = payload.reason; recommendation.decided_at = workflow.updated_at
    try: return workspace.save(workflow, payload.version, "recommendation_" + payload.decision, recommendation_id, {"reason": payload.reason or ""})
    except WorkspaceError as error: _raise(error)
