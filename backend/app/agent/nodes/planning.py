from app.agent.state import AgentState
from app.models.plan import CandidatePlan, CandidateTask
from app.models.task import Task


def _template_task(requirement, task_id: str, description: str, effort: str, dependencies: list[str]) -> CandidateTask:
    return CandidateTask(
        task_id=task_id,
        description=description,
        requirement_id=requirement.id,
        effort=effort,
        dependencies=dependencies,
    )


def _materialize_tasks(candidate: CandidatePlan) -> list[Task]:
    return [
        Task(
            id=task.task_id,
            description=task.description,
            dependencies=list(task.dependencies),
            effort=task.effort,
            requirement_ids=[task.requirement_id] if task.requirement_id else [],
        )
        for task in candidate.tasks
    ]


def build_candidate_plan(state: AgentState) -> CandidatePlan:
    """Derive an executable candidate plan from extracted requirements."""

    requirements = state.get("requirements", [])
    by_id = {requirement.id: requirement for requirement in requirements}
    tasks: list[CandidateTask] = []

    for index, requirement in enumerate(requirements, start=1):
        task_id = f"task_{index}"
        category_text = {
            "process": "Plan and sequence the work",
            "policy": "Compile the governing organizational policies",
            "approval": "Prepare the change package and obtain required approvals",
            "evidence": "Confirm evidence and success criteria",
            "definition": "Define the work precisely",
        }.get(requirement.category, "Complete the work")
        effort = {
            "process": "medium",
            "policy": "medium",
            "approval": "medium",
            "evidence": "small",
            "definition": "small",
        }.get(requirement.category, "small")
        dependencies = [f"task_{previous}" for previous in range(1, index)]
        tasks.append(
            _template_task(requirement, task_id, f"{category_text}: {requirement.text}", effort, dependencies)
        )

    return CandidatePlan(
        rationale=(
            "Tasks are derived from the extracted requirements and ordered "
            "so that dependencies are satisfied before dependent work begins."
        ),
        assumptions=[
            requirement.text
            for requirement in requirements
            if requirement.category == "evidence"
        ] or ["Missing organizational details must be gathered as evidence."],
        tasks=tasks,
    )


def create_plan_node(state: AgentState) -> AgentState:
    if state.get("candidate_plan") is None:
        candidate = build_candidate_plan(state)
    else:
        candidate = state["candidate_plan"]
        requirements = {requirement.id: requirement for requirement in state.get("requirements", [])}
        covered = {task.requirement_id for task in candidate.tasks if task.requirement_id}
        missing = [req for req in requirements.values() if req.id not in covered]
        if missing and not any(task.task_id.startswith("task_") for task in candidate.tasks):
            candidate = build_candidate_plan(state)

    return {
        "candidate_plan": candidate,
        "tasks": _materialize_tasks(candidate),
        "execution_metadata": {"plan": "created"},
    }