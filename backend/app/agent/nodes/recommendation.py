import logging

from app.agent.state import AgentState
from app.models.workflow import Recommendation

logger = logging.getLogger(__name__)


def _effort_rank(task) -> int:
    return {"small": 0, "medium": 1, "large": 2, "high": 3}.get(getattr(task, "effort", None) or "small", 1)


def _priority_rank(task) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(getattr(task, "priority", None) or "medium", 1)


def _readiness(tasks: list, completed: set[str]) -> tuple[set[str], set[str], dict[str, list[str]]]:
    """Compute ready/blocked task sets with the outstanding prerequisites."""
    by_id = {task.id: task for task in tasks}
    ready: set[str] = set()
    blocked: set[str] = set()
    waiting_on: dict[str, list[str]] = {}
    for task in tasks:
        if task.status == "completed":
            continue
        outstanding = [
            dep for dep in task.dependencies
            if dep in by_id and dep not in completed
        ]
        if outstanding:
            blocked.add(task.id)
            waiting_on[task.id] = outstanding
        else:
            ready.add(task.id)
    return ready, blocked, waiting_on


def _task_name(task) -> str:
    return getattr(task, "title", None) or task.description


def _unblocks_count(task_id: str, dependents: dict[str, list[str]]) -> int:
    return len(dependents.get(task_id, []))


def recommendation_node(state: AgentState) -> AgentState:
    """Recommend the most useful next action based on real task readiness.

    Scoring: dependency readiness first, then how many downstream tasks the
    action unblocks, declared priority, deadline pressure and effort. When
    several tasks are ready in parallel the recommendation says so.
    """
    tasks: list = state.get("tasks", [])
    completed = set(state.get("completed_tasks", []))
    optimization = state.get("optimization")
    critical_path = list(optimization.critical_path) if optimization else []
    pressure = (
        "high" if optimization and optimization.deadline_feasible is False else "normal"
    )
    workflow_id = state.get("workflow_id", "")

    if not tasks:
        return {
            "recommendation": Recommendation(
                recommendation_id=f"rec_{workflow_id}",
                workflow_id=workflow_id,
                action="no_action",
                reason="No plan tasks exist yet, so there is nothing to act on.",
                priority="low",
                critical_path=critical_path,
                deadline_pressure=pressure,
            ),
            "execution_metadata": {"recommendation": "completed"},
        }

    by_id = {task.id: task for task in tasks}
    dependents: dict[str, list[str]] = {}
    for task in tasks:
        for dep in task.dependencies:
            dependents.setdefault(dep, []).append(task.id)

    ready, _blocked, waiting_on = _readiness(tasks, completed)

    def complete_name(task_id: str) -> str:
        target = by_id.get(task_id)
        return _task_name(target) if target else task_id

    if not ready:
        # Everything unfinished is waiting on prerequisites that are not in
        # the plan's completed set — report the first blocker chain.
        victim = tasks[0]
        outstanding = waiting_on.get(victim.id, [])
        waiting_names = ", ".join(complete_name(dep) for dep in outstanding[:3]) or "upstream work"
        return {
            "recommendation": Recommendation(
                recommendation_id=f"rec_{workflow_id}",
                workflow_id=workflow_id,
                action="await_dependency",
                reason=(
                    f"'{_task_name(victim)}' cannot start until {waiting_names} "
                    "is completed. Finishing that work unblocks this task."
                ),
                affected_task=victim.id,
                blocked_by=outstanding[0] if outstanding else None,
                critical_path=critical_path,
                deadline_pressure=pressure,
                priority="medium",
            ),
            "execution_metadata": {"recommendation": "completed"},
        }

    # Score ready tasks: unblock potential, priority, critical path, effort.
    def score(task_id: str) -> tuple:
        task = by_id[task_id]
        on_critical_path = task_id in critical_path
        return (
            -_unblocks_count(task_id, dependents),
            0 if on_critical_path else 1,
            _priority_rank(task),
            _effort_rank(task),
            task_id,
        )

    ranked = sorted(ready, key=score)
    best_id = ranked[0]
    best = by_id[best_id]
    parallel = [tid for tid in ranked[1:] if score(tid)[:2] == score(best_id)[:2]][:3]
    unblocks = _unblocks_count(best_id, dependents)
    deliverable = getattr(best, "deliverable", None)
    criteria = getattr(best, "completion_criteria", []) or []

    reason_parts = [f"Begin '{_task_name(best)}'."]
    if unblocks:
        next_names = ", ".join(complete_name(dep) for dep in dependents[best_id][:2])
        reason_parts.append(
            f"It unblocks {unblocks} follow-up task(s) ({next_names})."
        )
    else:
        reason_parts.append("It has no outstanding prerequisites, so work can start now.")
    if parallel:
        parallel_names = ", ".join(complete_name(pid) for pid in parallel)
        reason_parts.append(
            f"You could also work on {parallel_names} in parallel."
        )
    expected = (
        f"Expected output: {deliverable}."
        if deliverable
        else ("Expected output: " + criteria[0] if criteria else "Expected output: the task's completion criteria are met.")
    )
    reason_parts.append(expected)

    return {
        "recommendation": Recommendation(
            recommendation_id=f"rec_{workflow_id}",
            workflow_id=workflow_id,
            action="start_task",
            reason=" ".join(reason_parts),
            affected_task=best_id,
            critical_path=critical_path,
            deadline_pressure=pressure,
            priority="high" if (best_id in critical_path or unblocks >= 2) else "medium",
        ),
        "execution_metadata": {"recommendation": "completed"},
    }