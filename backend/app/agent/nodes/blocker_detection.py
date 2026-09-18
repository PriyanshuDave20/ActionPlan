from app.agent.state import AgentState
from app.models.workflow import Blocker


def detect_blocker_node(state: AgentState) -> AgentState:
    blockers: list[Blocker] = []
    by_id = {task.id: task for task in state.get("tasks", [])}
    completed = set(state.get("completed_tasks", []))

    for task in state.get("tasks", []):
        incomplete_dependencies = [
            dep for dep in task.dependencies if dep not in completed
        ]
        if incomplete_dependencies:
            blockers.append(
                Blocker(
                    task_id=task.id,
                    type="dependency",
                    message=(
                        f"Task {task.id} waits on incomplete dependencies: "
                        f"{', '.join(incomplete_dependencies)}."
                    ),
                )
            )

    validation = state.get("plan_validation")
    if validation and not validation.valid:
        for issue in validation.errors:
            blockers.append(
                Blocker(task_id=issue.task_id or "", type="plan", message=issue.message)
            )

    uncovered = []
    covered = set()
    for task in state.get("tasks", []):
        covered.update(task.requirement_ids or [])

    for requirement in state.get("requirements", []):
        if requirement.id not in covered:
            uncovered.append(requirement.id)
    if uncovered:
        blockers.append(
            Blocker(
                task_id="",
                type="coverage",
                message=(
                    f"Plan does not cover requirement(s): {', '.join(sorted(uncovered))}."
                ),
            )
        )

    blocked = [
        blocker.task_id
        for blocker in blockers
        if blocker.task_id and blocker.type == "dependency"
    ]

    return {
        "detected_blockers": blockers,
        "blocked_tasks": blocked,
        "execution_metadata": {"blocker_detection": "completed"},
    }