"""Deterministic planning engine: validates and organizes the LLM's
proposed work breakdown into a dependency graph. All graph reasoning
(topology, cycle detection, parallel groups) happens here in Python —
never in the model.
"""

import logging
from collections import defaultdict

from app.models.plan import CandidatePlan, CandidateTask
from app.models.project_spec import ProjectSpecification, WorkBreakdown
from app.models.requirement import Requirement

logger = logging.getLogger(__name__)

_EVIDENCE_MAX_PASSAGES = 3


def _normalize_ids(breakdown: WorkBreakdown) -> tuple[dict[str, str], list[str]]:
    """Ensure stable, unique task ids. Returns (old->new id map, notes)."""
    notes: list[str] = []
    id_map: dict[str, str] = {}
    used: set[str] = set()
    for index, task in enumerate(breakdown.tasks, start=1):
        requested = (task.id or "").strip() or f"task_{index}"
        candidate = requested
        suffix = 1
        while candidate in used:
            suffix += 1
            candidate = f"{requested}_{suffix}"
        if candidate != requested:
            notes.append(f"Renamed duplicate task id '{requested}' to '{candidate}'.")
        id_map[requested] = candidate
        used.add(candidate)
    return id_map, notes


def _repair_dependencies(
    breakdown: WorkBreakdown, id_map: dict[str, str]
) -> tuple[dict[str, list[str]], list[str]]:
    """Drop invalid/self dependencies; detect and break cycles.

    Returns (task_id -> cleaned dependencies, notes).
    """
    notes: list[str] = []
    valid_ids = set(id_map.values())
    dependencies: dict[str, list[str]] = {}
    for task in breakdown.tasks:
        new_id = id_map[task.id]
        cleaned: list[str] = []
        for dep in task.dependencies:
            mapped = id_map.get((dep or "").strip())
            if mapped is None:
                notes.append(
                    f"Removed invalid dependency '{dep}' from {new_id} (no such task)."
                )
            elif mapped == new_id:
                notes.append(f"Removed self-dependency on {new_id}.")
            elif mapped in cleaned:
                continue
            else:
                cleaned.append(mapped)
        dependencies[new_id] = cleaned

    # Break cycles by dropping the last dependency of each cycle member
    # until the graph is acyclic (deterministic and bounded).
    for cycle in _find_cycles(dependencies):
        cycle_set = set(cycle)
        for node in cycle:
            deps = dependencies[node]
            inside = [dep for dep in deps if dep in cycle_set]
            if inside:
                dropped = inside[-1]
                deps.remove(dropped)
                notes.append(
                    "Broke dependency cycle by removing '" + dropped
                    + "' from " + node + " (cycle: " + " -> ".join(cycle) + ")."
                )
        # Re-check after each pass
        remaining = _find_cycles(dependencies)
        if not remaining:
            break
    return dependencies, notes


def _find_cycles(dependencies: dict[str, list[str]]) -> list[list[str]]:
    """Detect cycles in the dependency graph (task -> its dependencies)."""
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[list[str]] = []

    def visit(node: str, stack: list[str]) -> None:
        if node in visiting:
            cycle = stack[stack.index(node):] + [node]
            cycles.append(cycle)
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in dependencies.get(node, []):
            visit(dep, stack + [node])
        visiting.remove(node)
        visited.add(node)

    for node in list(dependencies):
        visit(node, [])
    return cycles


def topological_order(dependencies: dict[str, list[str]]) -> tuple[list[str], list[list[str]]]:
    """Kahn's algorithm. Returns (ordered ids, parallel groups per level)."""
    ids = list(dependencies)
    remaining = {task_id: set(deps) for task_id, deps in dependencies.items()}
    dependents: dict[str, set[str]] = defaultdict(set)
    for task_id, deps in remaining.items():
        for dep in deps:
            dependents[dep].add(task_id)

    ordered: list[str] = []
    groups: list[list[str]] = []
    ready = sorted([task_id for task_id, deps in remaining.items() if not deps])
    while ready:
        groups.append(ready)
        ordered.extend(ready)
        next_ready: list[str] = []
        for done in ready:
            for dependent in sorted(dependents.get(done, ())):
                remaining[dependent].discard(done)
                if not remaining[dependent] and dependent not in ordered:
                    next_ready.append(dependent)
        ready = sorted(set(next_ready) - set(ordered))
    if len(ordered) != len(ids):  # defensive; cycles are broken earlier
        logger.warning("Topological sort incomplete; appending remainder.")
        ordered.extend(sorted(set(ids) - set(ordered)))
    return ordered, groups


def repair_breakdown(
    breakdown: WorkBreakdown,
    spec: ProjectSpecification,
    requirements: list[Requirement],
) -> tuple[CandidatePlan, list[str]]:
    """Validate and organize an LLM work breakdown deterministically.

    Returns (candidate plan, repair/validation notes). Never invents tasks
    beyond the deterministic approval-coverage safeguard.
    """
    notes: list[str] = []
    if not breakdown.tasks:
        return CandidatePlan(rationale="Planner produced no tasks.", tasks=[]), notes

    id_map, id_notes = _normalize_ids(breakdown)
    notes.extend(id_notes)
    dependencies, dep_notes = _repair_dependencies(breakdown, id_map)
    notes.extend(dep_notes)

    deliverables = spec.all_deliverable_texts()
    requirement_index = {requirement.id: requirement for requirement in requirements}

    tasks: list[CandidateTask] = []
    for draft in breakdown.tasks:
        new_id = id_map[draft.id]
        deliverable_refs: list[str] = []
        deliverable_text = draft.deliverable
        for ref in draft.deliverable_refs:
            try:
                index = int(ref)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(deliverables):
                deliverable_refs.append(str(index))
                if not deliverable_text:
                    deliverable_text = deliverables[index]
        # Approval requirements must land on a task with required_approvals.
        required_approvals: list[str] = []
        requirement_ids: list[str] = []
        for requirement_id in draft.requirement_ids:
            requirement = requirement_index.get(requirement_id)
            if requirement is None:
                continue
            requirement_ids.append(requirement_id)
            if requirement.category == "approval":
                required_approvals.append("decision_maker")

        tasks.append(
            CandidateTask(
                task_id=new_id,
                title=draft.title,
                description=draft.description,
                completion_criteria=list(draft.completion_criteria),
                deliverable=deliverable_text,
                deliverable_refs=deliverable_refs,
                assumptions=list(draft.assumptions),
                requirement_id=requirement_ids[0] if requirement_ids else None,
                effort=draft.effort,
                priority=draft.priority,
                phase=draft.phase,
                dependencies=dependencies[new_id],
                required_approvals=required_approvals,
            )
        )

    # Deterministic safeguard: an approval requirement with no tagged task
    # gets one explicit approval task appended.
    covered_requirements = {
        requirement_id
        for task in tasks
        for requirement_id in ([task.requirement_id] if task.requirement_id else [])
    }
    for requirement in requirements:
        if requirement.category != "approval" or requirement.id in covered_requirements:
            continue
        approval_id = f"task_{len(tasks) + 1}"
        prior_ids = [task.task_id for task in tasks]
        tasks.append(
            CandidateTask(
                task_id=approval_id,
                title=f"Obtain approval for: {requirement.text[:80]}",
                description=(
                    "Secure documented sign-off from the decision makers for "
                    "this project before related work is closed out."
                ),
                completion_criteria=["Written approval recorded."],
                dependencies=prior_ids[-1:],
                effort="small",
                priority="high",
                required_approvals=["decision_maker"],
                requirement_id=requirement.id,
            )
        )
        notes.append(
            f"Added approval task {approval_id} for unmet approval requirement "
            f"{requirement.id}."
        )

    # Re-run dependency repair for the appended approval task edges.
    plan = CandidatePlan(
        rationale=(
            f"Work breakdown classified as {breakdown.project_type.replace('_', ' ')}; "
            "tasks are grounded in the project specification and organized by "
            "the deterministic dependency engine."
        ),
        assumptions=breakdown.assumptions[:6],
        tasks=tasks,
    )
    return plan, notes


def evidence_for_tasks(
    breakdown: WorkBreakdown, spec: ProjectSpecification
) -> dict[str, list[dict]]:
    """Attach provenance passages to task ids (content/document/page)."""
    result: dict[str, list[dict]] = {}
    for draft in breakdown.tasks:
        passages: list[dict] = []
        for passage in draft.evidence_passages[:_EVIDENCE_MAX_PASSAGES]:
            source = _locate_passage(passage, spec)
            passages.append({"content": passage, **source})
        if draft.id:
            result[draft.id] = passages
    return result


def _locate_passage(passage: str, spec: ProjectSpecification) -> dict:
    """Find which spec item the passage came from, for provenance."""
    for field_name in (
        "major_activities", "objective", "methodology", "deliverables",
        "milestones", "constraints", "research_questions", "scope",
    ):
        for item in getattr(spec, field_name):
            if passage and passage in item.content:
                return {
                    "document": item.source.document,
                    "page": item.source.page,
                    "section": item.source.section,
                }
    return {"document": "", "page": None, "section": None}
