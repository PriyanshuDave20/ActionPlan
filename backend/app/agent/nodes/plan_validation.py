from app.agent.state import AgentState
from app.agent.validation import MAX_PLAN_REVISIONS, validate_plan


def unique_ids(tasks: list) -> list[str]:
    """Return unique task ids in first-seen order."""
    seen: list[str] = []
    for task in tasks:
        if task.task_id not in seen:
            seen.append(task.task_id)
    return seen


def should_revise(state: AgentState) -> str:
    validation = state.get("plan_validation")
    if validation is None:
        return "execute_plan"
    if validation.valid:
        return "execute_plan"
    if state.get("plan_revision_count", 0) < MAX_PLAN_REVISIONS:
        return "revise_plan"
    return "plan_failed"


def validate_plan_node(state: AgentState) -> AgentState:
    candidate = state.get("candidate_plan")
    if candidate is None:
        return {"plan_validation": None, "execution_metadata": {"validation": "skipped"}}

    validation = validate_plan(
        candidate_plan=candidate,
        requirements=state.get("requirements", []),
        revision_count=state.get("plan_revision_count", 0),
    )
    return {
        "plan_validation": validation,
        "execution_metadata": {"validation": "completed"},
    }


def revise_plan_node(state: AgentState) -> AgentState:
    candidate = state.get("candidate_plan")
    if candidate is None:
        return {"execution_metadata": {"revision": "nothing_to_revise"}}

    requirements = {requirement.id: requirement for requirement in state.get("requirements", [])}
    covered = {task.requirement_id for task in candidate.tasks if task.requirement_id}
    uncovered = [req for req in requirements.values() if req.id not in covered]

    # Approval requirements that lack a task declaring required_approvals.
    missing_approvals = [
        req
        for req in requirements.values()
        if req.category == "approval"
        and not any(
            task.requirement_id == req.id and task.required_approvals
            for task in candidate.tasks
        )
    ]

    tasks = list(candidate.tasks)
    next_index = len(unique_ids(tasks)) + 1

    # Cover uncovered requirements with new tasks.
    for requirement in uncovered:
        from app.models.plan import CandidateTask

        tasks.append(
            CandidateTask(
                task_id=f"task_{next_index}",
                description=f"Complete the work required by {requirement.id}",
                requirement_id=requirement.id,
                effort="small",
                dependencies=[],
            )
        )
        next_index += 1

    # Add explicit approval tasks for approval requirements missing one.
    for requirement in missing_approvals:
        from app.models.plan import CandidateTask

        tasks.append(
            CandidateTask(
                task_id=f"task_{next_index}",
                description=f"Obtain approval for {requirement.id}",
                requirement_id=requirement.id,
                effort="small",
                dependencies=[],
                required_approvals=["decision_maker"],
            )
        )
        next_index += 1

    candidate.tasks = tasks
    revision = state.get("plan_revision_count", 0) + 1
    return {
        "candidate_plan": candidate,
        "plan_revision_count": revision,
        "execution_metadata": {"revision": revision},
    }


def plan_failed_node(state: AgentState) -> AgentState:
    """Record an explicit plan-failure state instead of executing an invalid plan.

    Routes to ``update_memory`` so the failure is persisted and visible to
    callers and the UI via ``execution_metadata`` and ``plan_validation``.
    """
    validation = state.get("plan_validation")
    summary = getattr(validation, "summary", "Plan validation failed.")
    return {
        "execution_metadata": {
            "plan_failed": True,
            "validation": "failed",
            "failure_reason": summary,
        }
    }
