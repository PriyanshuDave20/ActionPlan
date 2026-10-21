from fastapi import APIRouter, Depends, HTTPException, Header

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service
from app.api.dependencies import get_workspace
from app.models.work_request import WorkRequestInput
from app.models.workflow import ContinueRequest, WorkflowState, WorkflowExecutionState
from app.workspace import WorkspaceStore

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=WorkflowState, status_code=201)
def create_goal(
    payload: WorkRequestInput,
    service: AgentService = Depends(get_agent_service),
    workspace: WorkspaceStore = Depends(get_workspace),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    sync: bool = False,
) -> WorkflowState:
    # Check for existing workflow with the same idempotency key
    if idempotency_key:
        existing = workspace.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing
    
    if sync:
        workflow = service.create_workflow_sync(payload)
    else:
        workflow = service.create_workflow(payload)
    result = workspace.ensure(workflow)
    
    # Store idempotency key if provided
    if idempotency_key and result:
        workspace.set_idempotency_key(idempotency_key, result.workflow_id)
    
    return result


@router.post("/{workflow_id}/continue", response_model=WorkflowState)
def continue_goal(
    workflow_id: str,
    payload: ContinueRequest | None = None,
    service: AgentService = Depends(get_agent_service),
) -> WorkflowState:
    workflow = service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    return service.continue_workflow(workflow, payload.completed_task_ids if payload else [])


@router.get("/{workflow_id}/status", response_model=dict)
def get_workflow_status(
    workflow_id: str,
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """Get the execution status of a workflow."""
    workflow = service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    
    return {
        "workflow_id": workflow.workflow_id,
        "execution_state": workflow.execution_state.value,
        "execution_error": workflow.execution_error,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }
