from app.agent.state import AgentState
from app.models.workflow import Recommendation


def recommendation_node(state: AgentState) -> AgentState:
    completed = set(state.get("completed_tasks", []))
    by_id = {task.id: task for task in state.get("tasks", [])}
    blocked = set(state.get("blocked_tasks", []))
    optimization = state.get("optimization")
    critical_path = list(optimization.critical_path) if optimization else []

    pressure = (
        "high"
        if optimization and optimization.deadline_feasible is False
        else "normal"
    )
    priority = "high" if critical_path else "medium"

    current_task = state.get("current_task")
    candidate = by_id.get(current_task)

    if candidate and candidate.id in blocked:
        dependency = next(
            (dep for dep in candidate.dependencies if dep not in completed),
            None,
        )
        return {
            "recommendation": Recommendation(
                action="await_dependency",
                reason=(
                    f"Task {candidate.id} cannot begin until its dependencies complete."
                ),
                affected_task=candidate.id,
                blocked_by=dependency or candidate.id,
                role=candidate.role or "Requesting owner",
                critical_path=critical_path,
                deadline_pressure=pressure,
                priority=priority,
            ),
            "execution_metadata": {"recommendation": "completed"},
        }

    priority_tasks = [
        task
        for task in state.get("tasks", [])
        if task.id not in completed and task.id not in blocked
    ]

    if priority_tasks:
        task = priority_tasks[0]
        work_request = state.get("work_request")
        role = task.role or (
            work_request.people[0].name if work_request and work_request.people else None
        ) or "Requesting owner"
        return {
            "recommendation": Recommendation(
                action="start_task",
                reason=f"Start task {task.id} next: {task.description}.",
                affected_task=task.id,
                role=role,
                critical_path=critical_path,
                deadline_pressure=pressure,
                priority=priority,
            ),
            "execution_metadata": {"recommendation": "completed"},
        }

    return {
        "recommendation": Recommendation(
            action="no_action",
            reason="All planned work is complete.",
            affected_task=current_task,
            critical_path=critical_path,
            deadline_pressure="none",
            priority="low",
        ),
        "execution_metadata": {"recommendation": "completed"},
    }