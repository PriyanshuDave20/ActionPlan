from uuid import uuid4
import threading
import json
import boto3
import logging

from app.agent.graph import build_graph
from app.agent.state import AgentState
from app.memory.interface import MemoryInterface
from app.models.work_request import WorkRequestInput
from app.models.workflow import WorkflowState, WorkflowSummary, WorkflowExecutionState
from app.config import get_settings

logger = logging.getLogger(__name__)


class WorkflowNotFoundError(RuntimeError):
    """The requested workflow does not exist in persistent memory."""


class EnqueueError(RuntimeError):
    """The workflow could not be queued for background execution."""


def _project_title(payload: WorkRequestInput) -> str:
    return (payload.title or payload.goal).strip() or "Untitled project"


def _generate_workflow_id(title: str) -> str:
    slug = "".join(character for character in title.lower() if character.isalnum() or character.isspace())
    slug = "-".join(slug.split())[:40]
    return f"wf_{slug or 'goal'}_{uuid4().hex[:8]}"


def _worker_id() -> str:
    """Generate a unique worker ID for this process."""
    return f"worker-{uuid4().hex[:8]}"


def _send_workflow_job(queue_url: str, region: str, message: dict) -> str:
    """Send one workflow job message to SQS. Returns the SQS MessageId.

    Module-level so tests can stub SQS without touching AWS.
    """
    sqs = boto3.client("sqs", region_name=region)
    response = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message))
    return response.get("MessageId", "")


class AgentService:
    def __init__(self, llm, retriever, memory: MemoryInterface) -> None:
        self.llm = llm
        self.retriever = retriever
        self.memory = memory
        self.graph = build_graph(llm, retriever, memory)
        self._worker_id = f"worker-{uuid4().hex[:8]}"

    def create_workflow(self, goal_or_input: str | WorkRequestInput) -> WorkflowState:
        """Create a new workflow in QUEUED state and return it immediately.
        
        The actual execution will be triggered asynchronously via the queue worker.
        """
        if isinstance(goal_or_input, str):
            payload = WorkRequestInput(goal=goal_or_input)
        else:
            payload = goal_or_input

        title = _project_title(payload)
        workflow_id = _generate_workflow_id(title)
        
        # Create workflow in QUEUED state
        workflow = WorkflowState(
            workflow_id=workflow_id,
            project_title=title,
            original_goal=payload.goal,
            work_request=None,  # Will be populated during execution
            execution_state=WorkflowExecutionState.QUEUED,
        )
        
        # Save the workflow to memory
        self.memory.save_workflow(workflow)
        
        # Trigger async execution (will be handled by queue worker)
        self._trigger_async_execution(workflow_id=workflow.workflow_id, payload=payload)
        
        return workflow

    def create_workflow_sync(self, goal_or_input: str | WorkRequestInput) -> WorkflowState:
        """Create and execute a workflow synchronously (for testing)."""
        if isinstance(goal_or_input, str):
            payload = WorkRequestInput(goal=goal_or_input)
        else:
            payload = goal_or_input

        title = _project_title(payload)
        workflow_id = _generate_workflow_id(title)
        
        # Create workflow in QUEUED state
        workflow = WorkflowState(
            workflow_id=workflow_id,
            project_title=title,
            original_goal=payload.goal,
            work_request=None,
            execution_state=WorkflowExecutionState.QUEUED,
        )
        
        self.memory.save_workflow(workflow)
        
        # Execute synchronously
        return self._execute_workflow_sync(workflow_id, payload)

    def _trigger_async_execution(self, workflow_id: str, payload: WorkRequestInput) -> None:
        """Enqueue the workflow for background execution.

        In production (when WORKFLOW_QUEUE_URL is set), the complete validated
        request payload is sent to SQS. For local development without a queue,
        execution runs in a daemon thread as an explicitly configured fallback.

        The workflow is persisted (as QUEUED) before this call. If enqueueing
        fails, the workflow is transitioned to FAILED so no orphaned QUEUED
        record is left waiting for a worker that will never come, and the
        error is re-raised for the caller to surface.
        """
        settings = get_settings()
        queue_url = settings.workflow_queue_url

        if queue_url:
            message = {
                "workflow_id": workflow_id,
                "payload": payload.model_dump(mode="json"),
            }
            try:
                message_id = _send_workflow_job(queue_url, settings.aws_region, message)
            except Exception as exc:
                logger.error("Failed to enqueue workflow %s: %s", workflow_id, exc)
                self._persist_failure(workflow_id, payload.goal, f"Failed to enqueue workflow: {exc}")
                raise EnqueueError(f"Failed to enqueue workflow: {exc}") from exc
            logger.info("Queued workflow %s (MessageId=%s)", workflow_id, message_id)
            return

        # Local development fallback: daemon thread (never used in Lambda,
        # where WORKFLOW_QUEUE_URL is always configured).
        def execute_in_background():
            try:
                self._execute_workflow_sync(workflow_id, payload)
            except Exception as exc:
                logger.exception("Background execution failed for %s", workflow_id)

        thread = threading.Thread(target=execute_in_background, daemon=True)
        thread.start()

    def _persist_failure(self, workflow_id: str, goal: str, error: str) -> None:
        """Persist a terminal FAILED state with a safe error description."""
        workflow = self.memory.get_workflow(workflow_id)
        if workflow is None:
            workflow = WorkflowState(
                workflow_id=workflow_id,
                original_goal=goal,
                execution_state=WorkflowExecutionState.QUEUED,
            )
        workflow.execution_state = WorkflowExecutionState.FAILED
        workflow.execution_error = error
        self.memory.save_workflow(workflow)

    def _execute_claimed(self, workflow_id: str, payload: WorkRequestInput, claimed: WorkflowState) -> WorkflowState:
        """Run the graph for an already-claimed workflow and persist the outcome.

        COMPLETED is written only after the graph succeeds; any execution
        error is persisted as FAILED (with the message) before re-raising so
        the workflow never gets stuck in RUNNING.
        """
        initial_state = {
            "workflow_id": workflow_id,
            "project_title": _project_title(payload),
            "original_goal": payload.goal,
            "work_request_input": payload,
            "incoming_completed_task_ids": [],
            "completed_tasks": [],
            "plan_revision_count": 0,
            "execution_metadata": dict(claimed.execution_metadata or {}),
        }

        try:
            result = self.graph.invoke(initial_state)
        except Exception as exc:
            logger.exception("Workflow %s execution failed", workflow_id)
            self._persist_failure(workflow_id, payload.goal, str(exc))
            raise

        workflow = self._to_workflow_state(result)
        workflow.execution_state = WorkflowExecutionState.COMPLETED
        # The graph's memory node replaces execution_metadata with a minimal
        # dict; keep any user-added entries (e.g. ingested documents).
        workflow.execution_metadata = {
            **claimed.execution_metadata,
            **workflow.execution_metadata,
        }
        # COMPLETED is durable only once this save succeeds.
        self.memory.save_workflow(workflow)
        return workflow

    def _execute_workflow_sync(self, workflow_id: str, payload: WorkRequestInput) -> WorkflowState:
        """Claim and execute a workflow synchronously (local/testing path)."""
        claimed = self.memory.claim_workflow_for_execution(workflow_id, self._worker_id)
        if not claimed:
            raise RuntimeError(f"Could not claim workflow {workflow_id} for execution")
        return self._execute_claimed(workflow_id, payload, claimed)

    def execute_queued_workflow(
        self,
        workflow_id: str,
        payload: WorkRequestInput | None = None,
    ) -> WorkflowState | None:
        """Execute a queued workflow (called by the SQS worker).

        Uses the complete request payload delivered with the queue message
        when available; falls back to the persisted ``work_request`` so no
        user-provided field (people, deadline, priority, constraints,
        resources, success criteria) is silently discarded.

        Returns the completed workflow, or ``None`` when the workflow could
        not be claimed (duplicate delivery / already running) — an idempotent
        skip. Raises :class:`WorkflowNotFoundError` for a missing record so
        the worker can treat it as a permanent failure instead of leaving a
        message to retry forever.
        """
        workflow = self.memory.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found in persistent memory.")

        if payload is None:
            request = workflow.work_request
            payload = WorkRequestInput(
                title=workflow.project_title,
                goal=workflow.original_goal,
                people_involved=request.people if request else [],
                deadline=request.deadline if request else None,
                priority=request.priority if request else "medium",
                current_status=request.current_status if request else None,
                constraints=request.constraints if request else [],
                resources=request.resources if request else [],
                success_criteria=request.success_criteria if request else [],
            )

        claimed = self.memory.claim_workflow_for_execution(workflow_id, self._worker_id)
        if not claimed:
            # Duplicate SQS delivery or another worker holds the claim.
            logger.info("Workflow %s not claimable (not QUEUED); skipping.", workflow_id)
            return None
        return self._execute_claimed(workflow_id, payload, claimed)

    def rebuild_workflow(self, workflow: WorkflowState) -> WorkflowState:
        """Re-run analysis for an existing workflow, preserving its identity and attachments."""
        request = workflow.work_request
        payload = WorkRequestInput(
            title=workflow.project_title,
            goal=workflow.original_goal,
            people_involved=request.people if request else [],
            deadline=request.deadline if request else None,
            priority=request.priority if request else "medium",
            current_status=request.current_status if request else None,
            constraints=request.constraints if request else [],
            resources=request.resources if request else [],
            success_criteria=request.success_criteria if request else [],
        )
        result = self.graph.invoke({
            "workflow_id": workflow.workflow_id,
            "project_title": workflow.project_title,
            "original_goal": workflow.original_goal,
            "work_request_input": payload,
            "incoming_completed_task_ids": [],
            "completed_tasks": workflow.completed_tasks,
            "execution_metadata": workflow.execution_metadata,
        })
        rebuilt = self._to_workflow_state(result)
        rebuilt.execution_state = WorkflowExecutionState.COMPLETED
        # The graph's final memory node replaces execution_metadata with a
        # minimal dict, which drops the ingested-documents list and other
        # user-added entries. Restore them so the UI keeps showing documents.
        rebuilt.execution_metadata = {
            **workflow.execution_metadata,
            **rebuilt.execution_metadata,
        }
        # The graph's memory node already wrote a QUEUED-defaulted copy to
        # the durable store while invoking. This must be the final write so
        # the status endpoint reports COMPLETED instead of QUEUED.
        self.memory.save_workflow(rebuilt)
        return rebuilt

    def continue_workflow(
        self,
        workflow_id: str | WorkflowState,
        completed_task_ids: list[str] | None = None,
    ) -> WorkflowState | None:
        if isinstance(workflow_id, str):
            workflow = self.memory.get_workflow(workflow_id)
            if workflow is None:
                return None
        else:
            workflow = workflow_id
        state = self._to_agent_state(workflow)
        state["incoming_completed_task_ids"] = list(completed_task_ids or [])
        result = self.graph.invoke(state)
        continued = self._to_workflow_state(result)
        # The graph's memory node wrote a QUEUED-defaulted copy to the
        # durable store; persist the corrected state so polling never sees
        # a regressed workflow. Preserve user-added metadata the same way.
        continued.execution_state = workflow.execution_state
        continued.execution_metadata = {
            **workflow.execution_metadata,
            **continued.execution_metadata,
        }
        self.memory.save_workflow(continued)
        return continued

    def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        return self.memory.get_workflow(workflow_id)

    def list_workflows(self) -> list[WorkflowSummary]:
        return [
            _to_summary(workflow)
            for workflow in self.memory.list_workflows()
        ]

    @staticmethod
    def _to_agent_state(workflow: WorkflowState) -> AgentState:
        state: AgentState = {
            "workflow_id": workflow.workflow_id,
            "project_title": workflow.project_title,
            "original_goal": workflow.original_goal,
            "work_request": workflow.work_request,
            "work_request_input": None,
            "project_specification": workflow.project_specification,
            "objective_analysis": workflow.objective_analysis,
            "goal_analysis": workflow.goal_analysis,
            "planner_steps": workflow.planner_steps,
            "procedure_analysis": workflow.procedure_analysis,
            "procedures": workflow.procedures,
            "requirements": workflow.requirements,
            "candidate_plan": workflow.candidate_plan,
            "plan_validation": workflow.plan_validation,
            "plan_revision_count": workflow.plan_revision_count,
            "optimization": workflow.optimization,
            "tasks": workflow.tasks,
            "completed_tasks": workflow.completed_tasks,
            "blocked_tasks": workflow.blocked_tasks,
            "current_task": workflow.current_task,
            "current_state": workflow.current_state,
            "function_definitions": workflow.function_definitions,
            "retrieved_documents": workflow.retrieved_documents,
            "targeted_evidence": workflow.targeted_evidence,
            "targeted_by_requirement": workflow.targeted_by_requirement,
            "detected_blockers": workflow.detected_blockers,
            "recommendation": workflow.recommendation,
            "memory_context": workflow.memory_context,
            "execution_metadata": workflow.execution_metadata,
        }
        return state

    @staticmethod
    def _to_workflow_state(state: AgentState) -> WorkflowState:
        mapping = {
            "project_title": "project_title",
            "work_request": "work_request",
            "project_specification": "project_specification",
            "objective_analysis": "objective_analysis",
            "goal_analysis": "goal_analysis",
            "planner_steps": "planner_steps",
            "procedure_analysis": "procedure_analysis",
            "procedures": "procedures",
            "requirements": "requirements",
            "candidate_plan": "candidate_plan",
            "plan_validation": "plan_validation",
            "plan_revision_count": "plan_revision_count",
            "optimization": "optimization",
            "tasks": "tasks",
            "completed_tasks": "completed_tasks",
            "blocked_tasks": "blocked_tasks",
            "current_task": "current_task",
            "current_state": "current_state",
            "function_definitions": "function_definitions",
            "retrieved_documents": "retrieved_documents",
            "targeted_evidence": "targeted_evidence",
            "targeted_by_requirement": "targeted_by_requirement",
            "detected_blockers": "detected_blockers",
            "recommendation": "recommendation",
            "memory_context": "memory_context",
            "execution_metadata": "execution_metadata",
        }
        workflow = WorkflowState(
            workflow_id=state.get("workflow_id", ""),
            project_title=state.get("project_title"),
            original_goal=state.get("original_goal", ""),
        )
        for state_key, workflow_key in mapping.items():
            value = state.get(state_key)
            if value is not None:
                setattr(workflow, workflow_key, value)
        return workflow


def _to_summary(workflow: WorkflowState) -> WorkflowSummary:
    work_request = workflow.work_request
    return WorkflowSummary(
        workflow_id=workflow.workflow_id,
        title=workflow.project_title or workflow.original_goal,
        goal=workflow.original_goal,
        updated_at=workflow.updated_at,
        deadline=work_request.deadline if work_request else None,
        priority=(work_request.priority or "medium") if work_request else "medium",
        execution_state=workflow.execution_state.value,
        total_tasks=len(workflow.tasks),
        completed_tasks=len([
            task for task in workflow.tasks if task.status == "completed"
        ]),
        blocker_count=len(workflow.detected_blockers),
        recommendation_action=(
            workflow.recommendation.action if workflow.recommendation else None
        ),
    )
