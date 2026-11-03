"""Intelligent work breakdown: transforms the structured project
specification into a hierarchical, dependency-aware plan.

The LLM proposes phases, tasks and dependencies grounded in the extracted
specification; deterministic Python code validates identifiers, repairs
dependencies, breaks cycles, computes the topological order and attaches
evidence provenance. The number of tasks follows the actual project scope —
there is no fixed template.
"""

import logging

from app.agent.planning_engine import (
    evidence_for_tasks,
    repair_breakdown,
    topological_order,
)
from app.agent.state import AgentState
from app.llm.provider import LLMProvider
from app.models.evidence import Evidence
from app.models.plan import CandidatePlan
from app.models.project_spec import ProjectSpecification, WorkBreakdown
from app.models.requirement import Requirement
from app.models.task import Task

logger = logging.getLogger(__name__)


def _spec_from_state(state: AgentState) -> ProjectSpecification:
    data = state.get("project_specification")
    if isinstance(data, dict):
        try:
            return ProjectSpecification.model_validate(data)
        except Exception:
            logger.exception("Invalid project specification in state; treating as empty")
    return ProjectSpecification(title=state.get("original_goal", ""))


def _evidence_summary(state: AgentState, limit: int = 8) -> str:
    lines: list[str] = []
    for evidence in (state.get("retrieved_documents") or [])[:limit]:
        source = evidence.source or "unknown"
        page = f" p{evidence.page}" if evidence.page else ""
        lines.append(f"- [{source}{page}] {evidence.content[:200]}")
    return "\n".join(lines) if lines else "(no requirement evidence retrieved)"


def build_work_breakdown_node(state: AgentState, llm: LLMProvider) -> AgentState:
    if state.get("candidate_plan") is not None:
        return {"execution_metadata": {"plan": "reused"}}

    spec = _spec_from_state(state)
    requirements: list[Requirement] = state.get("requirements", [])
    evidence = _evidence_summary(state)

    try:
        breakdown = llm.build_work_breakdown(spec, requirements, evidence)
    except Exception:
        logger.exception("Work breakdown generation failed")
        return {
            "candidate_plan": CandidatePlan(
                rationale="Work breakdown generation failed; no tasks could be produced.",
                tasks=[],
            ),
            "execution_metadata": {"plan": "failed"},
        }

    candidate, notes = repair_breakdown(breakdown, spec, requirements)

    # Deterministic graph organization: execution order and parallel groups.
    dependencies = {task.task_id: list(task.dependencies) for task in candidate.tasks}
    order, parallel_groups = topological_order(dependencies)

    plan_metadata: dict = {
        "plan": "created",
        "planning_notes": notes,
        "topological_order": order,
        "parallel_groups": parallel_groups,
        "project_type": breakdown.project_type,
        "open_questions": breakdown.open_questions,
    }

    if not candidate.tasks:
        plan_metadata["plan"] = "empty"

    return {
        "candidate_plan": candidate,
        "tasks": _materialize_tasks(candidate, breakdown, spec),
        "execution_metadata": plan_metadata,
    }


def _materialize_tasks(
    candidate: CandidatePlan,
    breakdown: WorkBreakdown,
    spec: ProjectSpecification,
) -> list[Task]:
    evidence_map = evidence_for_tasks(breakdown, spec)
    deliverables = spec.all_deliverable_texts()
    tasks: list[Task] = []
    for candidate_task in candidate.tasks:
        passages = evidence_map.get(candidate_task.task_id, [])
        tasks.append(
            Task(
                id=candidate_task.task_id,
                title=candidate_task.title,
                description=candidate_task.description,
                completion_criteria=list(candidate_task.completion_criteria),
                deliverable=candidate_task.deliverable,
                deliverable_refs=[
                    deliverables[int(ref)]
                    for ref in candidate_task.deliverable_refs
                    if ref.isdigit() and int(ref) < len(deliverables)
                ],
                assumptions=list(candidate_task.assumptions),
                dependencies=list(candidate_task.dependencies),
                effort=candidate_task.effort,
                priority=candidate_task.priority,
                required_approvals=list(candidate_task.required_approvals),
                requirement_ids=[candidate_task.requirement_id] if candidate_task.requirement_id else [],
                evidence=[
                    Evidence(
                        content=passage["content"],
                        source=passage.get("document") or None,
                        page=passage.get("page"),
                    )
                    for passage in passages
                ],
            )
        )
    return tasks
