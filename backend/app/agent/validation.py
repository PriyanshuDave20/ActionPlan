from app.models.plan import CandidatePlan, PlanValidationResult, ValidationIssue
from app.models.requirement import Requirement

MAX_PLAN_REVISIONS = 1


def _cycle_ids(tasks: list) -> list[str]:
    graph = {task.task_id: task.dependencies for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    found: list[str] = []

    def visit(node: str, stack: list[str]) -> None:
        if node in visiting:
            cycle = stack[stack.index(node):] + [node]
            found.append(" -> ".join(cycle))
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            visit(dependency, stack + [node])
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [])
    return found


def validate_plan(
    candidate_plan: CandidatePlan,
    requirements: list[Requirement],
    revision_count: int,
) -> PlanValidationResult:
    """Deterministic structural validation of the candidate plan."""

    tasks = candidate_plan.tasks
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    task_ids = {task.task_id for task in tasks}

    if len(task_ids) != len(tasks):
        errors.append(
            ValidationIssue(code="duplicate_task_ids", message="Task IDs must be unique.")
        )

    invalid_dependencies: list[str] = []
    for task in tasks:
        missing = set(task.dependencies) - task_ids
        if missing:
            invalid_dependencies.append(task.task_id)
            errors.append(
                ValidationIssue(
                    code="unknown_dependency",
                    message=(
                        f"Task {task.task_id} depends on unknown tasks: "
                        f"{sorted(missing)}."
                    ),
                    task_id=task.task_id,
                )
            )

    for cycle in _cycle_ids(tasks):
        errors.append(
            ValidationIssue(code="dependency_cycle", message=f"Dependency cycle: {cycle}")
        )

    sequencing_violations: list[str] = []
    index = {task.task_id: position for position, task in enumerate(tasks)}
    for task in tasks:
        for dependency in task.dependencies:
            if index.get(dependency, len(tasks) + 1) > index.get(task.task_id, 0):
                sequencing_violations.append(f"{task.task_id} -> {dependency}")

    uncovered_requirements: list[str] = []
    referenced = {task.requirement_id for task in tasks if task.requirement_id}
    for requirement in requirements:
        if requirement.id not in referenced:
            uncovered_requirements.append(requirement.id)
            errors.append(
                ValidationIssue(
                    code="uncovered_requirement",
                    message=(
                        f"Requirement {requirement.id} is not covered by any plan task."
                    ),
                )
            )

    missing_approvals: list[str] = []
    for requirement in requirements:
        if requirement.category != "approval":
            continue
        matching = [
            task for task in tasks if task.requirement_id == requirement.id
        ]
        if not matching or not any("approval" in task.description.lower() for task in matching):
            missing_approvals.append(requirement.id)
            errors.append(
                ValidationIssue(
                    code="missing_approval_task",
                    message=(
                        f"Requirement {requirement.id} needs an approval step "
                        "in the plan."
                    ),
                )
            )

    if sequencing_violations:
        warnings.append(
            ValidationIssue(
                code="sequencing_warning",
                message="Some tasks list dependencies that appear later in the plan.",
            )
        )

    issues = errors or warnings
    if errors:
        summary = "Plan is invalid and needs revision."
    elif warnings:
        summary = "Plan is valid with warnings."
    else:
        summary = "Plan is consistent and ready to execute."

    return PlanValidationResult(
        valid=not errors,
        summary=summary,
        errors=errors,
        warnings=warnings,
        invalid_dependencies=invalid_dependencies,
        missing_approvals=missing_approvals,
        sequencing_violations=sequencing_violations,
        uncovered_requirements=uncovered_requirements,
        revision_count=revision_count,
    )