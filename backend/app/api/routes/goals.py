from fastapi import APIRouter, Depends, HTTPException

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service
from app.models.work_request import WorkRequestInput
from app.models.workflow import ContinueRequest, WorkflowState

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=WorkflowState, status_code=201)
def create_goal(
    payload: WorkRequestInput,
    service: AgentService = Depends(get_agent_service),
) -> WorkflowState:
    return service.create_workflow(payload)


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