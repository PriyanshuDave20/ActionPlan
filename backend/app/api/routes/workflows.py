from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
import httpx

from app.config import get_settings
from app.integrations.jira import JiraIntegration
from app.integrations.models import ExecutionRequest, IntegrationResult
from app.integrations.slack import SlackIntegration

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service
from app.api.dependencies import get_workspace
from app.models.workflow import WorkflowState, WorkflowSummary
from app.models.workspace import PlanRevisionRequest, RecommendationDecision, TaskPatch, TaskTransition, WorkflowEvent, WorkflowEvidence, WorkflowUpdateRequest
from app.workspace import Conflict, NotFound, WorkspaceError, WorkspaceStore, transition_task

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _workspace_workflow(workflow_id: str, service: AgentService, workspace: WorkspaceStore) -> WorkflowState:
    """Resolve the workflow for read/update routes without executing the agent.

    The durable store (DynamoDB) is authoritative for asynchronously executed
    workflows: the worker writes COMPLETED there while the local SQLite
    workspace may still hold the pre-execution QUEUED copy. Prefer whichever
    copy is newer and keep the workspace in sync so optimistic-version saves
    (transitions, decisions) continue to work. Purely read-only: never
    builds or invokes the LangGraph.
    """
    local = None
    try:
        local = workspace.get(workflow_id)
    except NotFound:
        local = None

    durable = service.get_workflow(workflow_id)

    if durable is not None and (local is None or durable.updated_at > local.updated_at):
        return workspace.ensure(durable)
    if local is not None:
        return local
    if durable is not None:
        return workspace.ensure(durable)
    raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")


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


@router.post("/{workflow_id}/recommendations/{recommendation_id}/execute", response_model=WorkflowState)
async def execute_recommendation(
    workflow_id: str,
    recommendation_id: str,
    payload: ExecutionRequest,
    service: AgentService = Depends(get_agent_service),
    workspace: WorkspaceStore = Depends(get_workspace),
) -> WorkflowState:
    """Run an explicitly requested integration after a human accepts the recommendation."""
    workflow = _workspace_workflow(workflow_id, service, workspace)
    recommendation = workflow.recommendation
    if recommendation is None or recommendation.recommendation_id != recommendation_id:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    if recommendation.status != "accepted":
        raise HTTPException(
            status_code=409,
            detail="Only accepted recommendations can be sent to an integration.",
        )

    settings = get_settings()
    results: list[IntegrationResult] = []
    text = payload.message or (
        f"Recommendation for {workflow.original_goal}: {recommendation.action}. "
        f"{recommendation.reason}"
    )

    async with httpx.AsyncClient(timeout=15) as client:
        if payload.notify_slack:
            try:
                results.append(
                    await SlackIntegration(settings.slack_webhook_url, client).post_message(
                        text=text, channel=payload.channel
                    )
                )
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            except RuntimeError as error:
                raise HTTPException(status_code=502, detail=str(error)) from error

        if payload.create_jira_issue:
            if not payload.jira_project:
                raise HTTPException(status_code=400, detail="jira_project is required.")
            try:
                results.append(
                    await JiraIntegration(
                        base_url=settings.jira_base_url,
                        email=settings.jira_email,
                        api_token=settings.jira_api_token,
                        client=client,
                    ).create_issue(
                        project=payload.jira_project,
                        summary=recommendation.action[:240],
                        description=text,
                        issue_type=payload.jira_issue_type,
                    )
                )
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            except RuntimeError as error:
                raise HTTPException(status_code=502, detail=str(error)) from error

    if not results:
        raise HTTPException(status_code=400, detail="No integration was requested.")

    workflow.execution_metadata.setdefault("integrations", []).append(
        {
            "recommendation_id": recommendation_id,
            "at": datetime.now(timezone.utc).isoformat(),
            "results": [result.model_dump(mode="json") for result in results],
        }
    )
    return workspace.save(
        workflow,
        payload.version,
        "integration_executed",
        recommendation_id,
        {
            "providers": [result.provider for result in results],
            "ok": all(result.ok for result in results),
        },
        actor="user",
    )
