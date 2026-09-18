from app.agent.state import AgentState
from app.memory.interface import MemoryInterface
from app.models.workflow import WorkflowState, utc_now

_HISTORY_CACHE: dict[str, list[str]] = {}


def _memory_context(workflow: WorkflowState) -> list[str]:
    lines = [
        f"Workflow started with goal: {workflow.original_goal}",
        f"Workflow recommendation: {workflow.recommendation.reason if workflow.recommendation else 'pending'}",
    ]
    for task in workflow.tasks:
        status = "complete" if task.status == "completed" else "pending"
        lines.append(f"Task {task.id}: {task.description} ({status})")
    return lines


def schedule_chat_node():
    raise RuntimeError("schedule_chat_node is not part of the linear workflow")


def update_memory_node(state: AgentState, memory: MemoryInterface) -> AgentState:
    workflow = _state_to_workflow(state)
    memory.save_workflow(workflow)
    return {"memory_context": _memory_context(workflow), "execution_metadata": {"memory": "saved"}}


def _state_to_workflow(state: AgentState) -> WorkflowState:
    stored = WorkflowState(
        workflow_id=state.get("workflow_id", ""),
        original_goal=state.get("original_goal", ""),
        updated_at=utc_now(),
    )
    for key in (
        "objective_analysis",
        "goal_analysis",
        "planner_steps",
        "procedure_analysis",
        "procedures",
        "requirements",
        "candidate_plan",
        "plan_validation",
        "plan_revision_count",
        "optimization",
        "tasks",
        "completed_tasks",
        "blocked_tasks",
        "current_task",
        "current_state",
        "retrieved_documents",
        "targeted_evidence",
        "targeted_by_requirement",
        "detected_blockers",
        "recommendation",
        "memory_context",
        "execution_metadata",
        "work_request",
    ):
        if key in state:
            setattr(stored, key, state[key])
    return stored