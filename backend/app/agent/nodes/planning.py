"""Deterministic goal-derived fallback planning.

This module is no longer part of the primary graph: document-grounded
planning lives in ``work_breakdown`` + ``planning_engine``. These helpers
remain for direct callers and tests that need a plan without an LLM.
"""

from app.agent.state import AgentState
from app.models.plan import CandidatePlan, CandidateTask
from app.models.task import Task


def _materialize_tasks(candidate: CandidatePlan) -> list[Task]:
    return [
        Task(
            id=task.task_id,
            title=task.title,
            description=task.description,
            dependencies=list(task.dependencies),
            effort=task.effort,
            required_approvals=list(task.required_approvals),
            requirement_ids=[task.requirement_id] if task.requirement_id else [],
        )
        for task in candidate.tasks
    ]


def build_candidate_plan(state: AgentState) -> CandidatePlan:
    """Goal-derived deterministic fallback (no LLM, no requirement template).

    Produces a small, honest starting plan scoped to the goal text itself.
    """
    goal = state.get("original_goal", "the project")
    starter = [
        ("Clarify scope and success criteria", f"Confirm the scope, success criteria and constraints for {goal}."),
        ("Draft the work plan", f"Break {goal} into ordered work packages with owners."),
        ("Execute the core work", f"Carry out the main work required for {goal}."),
        ("Review outcomes and close out", f"Verify outcomes against the success criteria for {goal} and record sign-off."),
    ]
    tasks = [
        CandidateTask(
            task_id=f"task_{index}",
            title=title,
            description=description,
            completion_criteria=[f"{title} completed for {goal}."],
            dependencies=[f"task_{index - 1}"] if index > 1 else [],
            effort="medium" if index in (2, 3) else "small",
            required_approvals=["decision_maker"] if index == 4 else [],
        )
        for index, (title, description) in enumerate(starter, start=1)
    ]
    return CandidatePlan(
        rationale=(
            "No project documents were available, so this is a minimal "
            "goal-scoped starting plan rather than a document-grounded one."
        ),
        assumptions=["Scope derived from the goal text only; documents were not provided."],
        tasks=tasks,
    )