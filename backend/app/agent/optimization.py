from datetime import date

from app.models.optimization import OptimizationResult
from app.models.plan import CandidatePlan

_EFFORT_UNITS = {
    "small": 1,
    "medium": 2,
    "large": 3,
    "high": 4,
}


def _effort_units(level: str | None) -> int:
    return _EFFORT_UNITS.get(level or "small", 1)


def _critical_path(tasks: list, units) -> tuple[list[str], int]:
    """Longest dependency chain computed with dynamic programming."""

    by_id = {task.task_id: task for task in tasks}
    best: dict[str, tuple[int, list[str]]] = {}

    def solve(task_id: str) -> tuple[int, list[str]]:
        if task_id in best:
            return best[task_id]
        task = by_id[task_id]
        weight = _effort_units(getattr(task, "effort", None)) if units in ("task", None) else units.get(task_id, 1)
        if task.dependencies:
            candidate = max(
                (solve(dep) for dep in task.dependencies if dep in by_id),
                key=lambda item: item[0],
                default=(0, []),
            )
            best[task_id] = (candidate[0] + weight, candidate[1] + [task_id])
        else:
            best[task_id] = (weight, [task_id])
        return best[task_id]

    _, path = max((solve(task.task_id) for task in tasks), key=lambda item: item[0], default=(0, []))
    return path, sum(_effort_units(by_id[node].effort) for node in path)


def optimize_plan(
    candidate_plan: CandidatePlan,
    deadline: date | None,
    completed_task_ids: list[str],
) -> OptimizationResult:
    """Deterministic optimization: critical path, parallelism, deadline check."""

    tasks = candidate_plan.tasks
    critical_path, critical_path_effort = _critical_path(tasks, "task")
    critical_set = set(critical_path)

    layers: list[list[str]] = []
    remaining = sorted((task.task_id for task in tasks if task.task_id not in completed_task_ids),
                       key=lambda tid: sum(len(t.dependencies) for t in tasks if t.task_id == tid))
    by_id = {task.task_id: task for task in tasks}
    placed: set[str] = set()
    while True:
        layer = [
            tid for tid in remaining
            if tid not in placed
            and all(dep in placed for dep in by_id[tid].dependencies if dep not in completed_task_ids)
        ]
        if not layer:
            break
        layers.append(layer)
        placed.update(layer)

    parallel_chains = [
        [tid for tid in layer if tid not in critical_set]
        for layer in layers
    ]
    parallel_chains = [chain for chain in parallel_chains if chain]

    days_until_deadline: int | None = None
    if deadline is not None:
        days_until_deadline = (deadline - date.today()).days

    deadline_feasible: bool | None = None
    deadline_notes: str | None = None
    if days_until_deadline is not None:
        deadline_feasible = days_until_deadline >= critical_path_effort
        deadline_notes = (
            "Deadline is feasible at the current critical-path estimate."
            if deadline_feasible
            else "Deadline is at risk; parallelize or reduce effort."
        )

    notes = [
        f"Critical path: {len(critical_path)} task(s), {critical_path_effort} effort unit(s).",
    ]
    if parallel_chains:
        notes.append(f"{len(parallel_chains)} non-critical chain(s) can run in parallel.")

    return OptimizationResult(
        summary=(
            f"Critical path is {critical_path_effort} effort unit(s); "
            + (deadline_notes or "no deadline constraint provided.")
        ),
        critical_path=critical_path,
        critical_path_effort=critical_path_effort,
        parallel_chains=parallel_chains,
        days_until_deadline=days_until_deadline,
        deadline_feasible=deadline_feasible,
        deadline_notes=deadline_notes,
        notes=notes,
    )