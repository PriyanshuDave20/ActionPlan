from app.models.plan import CandidatePlan, PlanValidationResult, ValidationIssue
from app.models.project_spec import ProjectSpecification
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
    spec: ProjectSpecification | None = None,
) -> PlanValidationResult:
    """Deterministic structural validation of the candidate plan.

    When a project specification is supplied, deliverable coverage and task
    grounding are also validated so document-derived work is not dropped.
    """

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
        has_approval_step = any(
            bool(task.required_approvals) for task in matching
        )
        if not matching or not has_approval_step:
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

    # Document-grounded checks: every extracted deliverable must be covered
    # by at least one task, and tasks should state how completion is judged.
    uncovered_deliverables: list[str] = []
    if spec is not None:
        deliverables = spec.all_deliverable_texts()
        if deliverables and tasks:
            covered_refs = {
                ref for task in tasks for ref in task.deliverable_refs
            }
            covered_texts = {
                (task.deliverable or "").strip().lower() for task in tasks
            }
            for index, deliverable in enumerate(deliverables):
                if str(index) in covered_refs:
                    continue
                if deliverable.strip().lower() in covered_texts:
                    continue
                uncovered_deliverables.append(deliverable)
                errors.append(
                    ValidationIssue(
                        code="uncovered_deliverable",
                        message=(
                            f"Deliverable '{deliverable}' from the project "
                            "documents is not produced by any planned task."
                        ),
                    )
                )
        if tasks:
            unactionable = [
                task.task_id
                for task in tasks
                if not task.completion_criteria
                and len(task.description.strip()) < 20
            ]
            if unactionable:
                warnings.append(
                    ValidationIssue(
                        code="vague_task_description",
                        message=(
                            "Some tasks lack completion criteria and have "
                            "very short descriptions: "
                            + ", ".join(unactionable[:5])
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
        uncovered_deliverables=uncovered_deliverables,
        revision_count=revision_count,
    )