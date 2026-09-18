from fastapi import APIRouter, Depends, HTTPException

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service
from app.models.workflow import WorkflowState, WorkflowSummary

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(
    service: AgentService = Depends(get_agent_service),
) -> list[WorkflowSummary]:
    return service.list_workflows()


@router.get("/{workflow_id}", response_model=WorkflowState)
def get_workflow(
    workflow_id: str,
    service: AgentService = Depends(get_agent_service),
) -> WorkflowState:
    workflow = service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    return workflow