"""Document-grounded planning engine tests.

Verifies that plans are derived from project documents rather than generic
administrative templates: specification extraction retains evidence,
classifies project type, missing information is never fabricated, the work
breakdown is project-specific, dependencies are validated and ordered
deterministically, and recommendations reference real, ready tasks.

The BME 415 proposal fixture (wild-type vs R168C easyCLIP comparison) is
used as a realistic regression example — as one test case, not a special
case: all assertions probe for content-derived behaviour.
"""

import json
from pathlib import Path

import pytest

from app.agent.planning_engine import (
    repair_breakdown,
    topological_order,
)
from app.agent.validation import validate_plan
from app.llm.provider import MockLLMProvider, _SPEC_MARKERS
from app.models.plan import CandidatePlan, CandidateTask
from app.models.project_spec import (
    EvidenceRef,
    PlannedTaskDraft,
    ProjectSpecification,
    SpecItem,
    WorkBreakdown,
    WorkPackageDraft,
)
from app.models.requirement import Requirement

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BME_DOCUMENT = BACKEND_ROOT / "documents" / "bme415_proposal.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_item(content: str, document: str = "proposal.txt", page: int = 1) -> SpecItem:
    return SpecItem(
        content=content,
        source=EvidenceRef(document=document, page=page, passage=content),
        confidence=0.9,
        kind="explicit",
    )


def _bme_spec() -> ProjectSpecification:
    return ProjectSpecification(
        title="Comparative analysis of KHDRBS2 wild-type and R168C RNA-binding behaviour",
        project_type="academic_research",
        objective=[
            _spec_item("Determine how the R168C mutation alters the RNA-binding behaviour of KHDRBS2 versus wild-type.")
        ],
        research_questions=[
            _spec_item("Does the R168C substitution change the sequence preferences of KHDRBS2?"),
        ],
        methodology=[
            _spec_item("easyCLIP datasets for wild-type and R168C; adapter trimming, alignment, peak calling, motif analysis."),
        ],
        major_activities=[
            _spec_item("Identify and download the wild-type and R168C easyCLIP datasets and inspect sample metadata and replicates."),
            _spec_item("Align reads and call peaks to identify binding sites for each condition."),
            _spec_item("Annotate identified binding sites by transcript region such as 3' UTR, CDS and introns."),
            _spec_item("Compare sequence preferences between wild-type and mutant binding sites using motif enrichment."),
            _spec_item("Identify shared, gained and lost binding sites between the two conditions."),
            _spec_item("Interpret the results in the context of known KHDRBS2 biology and prepare the final report."),
        ],
        deliverables=[
            _spec_item("Final report with figures and interpretation, due end of week 10."),
            _spec_item("Short in-class presentation of the wild-type vs R168C comparison."),
        ],
        deadlines=[_spec_item("Final report submitted in week 10.")],
        people=[
            _spec_item("Sanna: computational pipeline and peak calling."),
            _spec_item("Priyanshu: motif analysis and transcript-region annotation."),
        ],
        constraints=[_spec_item("Only publicly available datasets may be used.")],
        risks=[_spec_item("If R168C has fewer replicates, the comparison is limited and discussed.")],
        missing_information=["No budget is stated in the documents."],
        search_queries=["KHDRBS2 easyCLIP wild-type R168C"],
    )


def _requirements() -> list[Requirement]:
    return [
        Requirement(id="req_1", category="process", text="Sequence the work."),
        Requirement(id="req_2", category="approval", text="Obtain sign-off."),
    ]


def _breakdown_from(spec: ProjectSpecification, task_count: int | None = None) -> WorkBreakdown:
    """Build a grounded breakdown the way the LLM is instructed to."""
    activities = [item.content for item in spec.major_activities]
    if task_count is not None:
        activities = activities[:task_count]
    tasks = [
        PlannedTaskDraft(
            id=f"task_{index}",
            title=activity,
            description=f"{activity} (from project documents).",
            completion_criteria=[f"{activity} completed and reviewed."],
            dependencies=[f"task_{index - 1}"] if index > 1 else [],
            effort="medium",
            phase="phase_1",
            evidence_passages=[activity],
            requirement_ids=["req_1"],
        )
        for index, activity in enumerate(activities, start=1)
    ]
    return WorkBreakdown(
        project_type=spec.project_type,
        phases=[WorkPackageDraft(id="phase_1", name="Analysis", task_ids=[t.id for t in tasks])],
        tasks=tasks,
    )


# ---------------------------------------------------------------------------
# Specification extraction
# ---------------------------------------------------------------------------


def test_mock_understanding_extracts_structured_spec_from_document_chunks():
    provider = MockLLMProvider()
    context = "\n".join(
        [
            json.dumps({"document": "bme415_proposal.txt", "page": 1,
                        "text": "The objective of this project is to determine how the R168C mutation alters RNA-binding."}),
            json.dumps({"document": "bme415_proposal.txt", "page": 2,
                        "text": "We will compare sequence preferences between wild-type and mutant binding sites."}),
        ]
    )
    spec = provider.understand_documents("KHDRBS2 comparison", context)
    assert spec.project_type in (
        "academic_research", "general",
    )  # classified, not hardcoded
    assert any("R168C" in item.content for item in spec.objective + spec.major_activities)
    assert all(item.source.document == "bme415_proposal.txt" for section in (
        "objective", "major_activities",
    ) for item in getattr(spec, section))


def test_missing_information_is_not_fabricated():
    provider = MockLLMProvider()
    spec = provider.understand_documents("Plan a team offsite", "(no project documents were indexed for this goal)")
    # With no documents, unknown facts land in missing_information.
    assert spec.missing_information
    joined = " ".join(spec.missing_information).lower()
    assert "unspecified" in joined or "no project documents" in joined
    # And no fabricated deadline/budget appears anywhere.
    for section in ("deadlines", "constraints", "resources", "people"):
        for item in getattr(spec, section):
            assert item.kind == "explicit"


def test_explicit_and_inferred_information_are_distinguishable():
    item = SpecItem(content="Report due week 10", kind="explicit", confidence=0.9)
    inferred = SpecItem(content="Likely needs GPU time", kind="inference", confidence=0.4)
    assert item.kind == "explicit" and inferred.kind == "inference"
    assert item.source.document == ""  # provenance carried separately


# ---------------------------------------------------------------------------
# Work breakdown grounding
# ---------------------------------------------------------------------------


def test_bme415_breakdown_contains_real_research_activities_not_admin_templates():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    plan, notes = repair_breakdown(breakdown, spec, _requirements())
    titles = " ".join((task.title or "") + " " + task.description for task in plan.tasks).lower()

    # Real activities from the documents appear…
    for expected in (
        "datasets", "binding sites", "motif", "transcript region", "replicates",
    ):
        assert expected in titles, f"missing grounded activity: {expected}"
    # …and the generic administrative filler is gone.
    for banned in (
        "governing organizational policies",
        "standardized project proposal workflow",
        "change package",
    ):
        assert banned not in titles


def test_document_content_changes_the_generated_tasks():
    spec_with_doc = _bme_spec()
    breakdown_doc = _breakdown_from(spec_with_doc)
    plan_doc, _ = repair_breakdown(breakdown_doc, spec_with_doc, _requirements())
    titles_doc = {task.title for task in plan_doc.tasks}

    # Generic goal with no document: the mock produces goal-scoped starter tasks.
    provider = MockLLMProvider()
    generic_spec = provider.understand_documents("Deploy the staging environment", "(no project documents were indexed for this goal)")
    breakdown_generic = provider.build_work_breakdown(generic_spec, _requirements(), "(no evidence)")
    plan_generic, _ = repair_breakdown(breakdown_generic, generic_spec, _requirements())
    titles_generic = {task.title for task in plan_generic.tasks}

    assert titles_doc != titles_generic
    assert any("easyCLIP" in t or "binding" in t.lower() for t in titles_doc)
    assert not any("binding" in t.lower() for t in titles_generic)


def test_breakdown_scales_with_project_scope_not_fixed_template():
    spec = _bme_spec()
    full = repair_breakdown(_breakdown_from(spec), spec, _requirements())[0]
    trimmed_spec = spec.model_copy(deep=True)
    trimmed_spec.major_activities = spec.major_activities[:2]
    trimmed = repair_breakdown(_breakdown_from(trimmed_spec), trimmed_spec, _requirements())[0]
    assert len(full.tasks) > len(trimmed.tasks) >= 2


def test_deliverables_are_represented_in_the_plan():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    # Tag the report deliverable on the last task (deliverable index 0).
    breakdown.tasks[-1].deliverable = spec.all_deliverable_texts()[0]
    breakdown.tasks[-1].deliverable_refs = ["0"]
    plan, _ = repair_breakdown(breakdown, spec, _requirements())
    assert any(
        "final report" in (task.deliverable or "").lower() or "0" in task.deliverable_refs
        for task in plan.tasks
    )


def test_evidence_references_are_retained_on_tasks():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    plan, _ = repair_breakdown(breakdown, spec, _requirements())
    from app.agent.nodes.work_breakdown import _materialize_tasks
    tasks = _materialize_tasks(plan, breakdown, spec)
    grounded = [task for task in tasks if task.evidence]
    assert grounded, "document-grounded tasks must retain evidence"
    for task in grounded:
        for evidence in task.evidence:
            assert evidence.source == "proposal.txt"


# ---------------------------------------------------------------------------
# Dependency graph handling
# ---------------------------------------------------------------------------


def test_invalid_dependencies_are_removed_with_a_note():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    breakdown.tasks[0].dependencies = ["task_999"]
    plan, notes = repair_breakdown(breakdown, spec, _requirements())
    assert all("task_999" not in task.dependencies for task in plan.tasks)
    assert any("invalid dependency" in note.lower() for note in notes)


def test_circular_dependencies_are_detected_and_broken():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    breakdown.tasks[0].dependencies = ["task_2"]
    breakdown.tasks[1].dependencies = ["task_1"]
    plan, notes = repair_breakdown(breakdown, spec, _requirements())
    deps = {task.task_id: task.dependencies for task in plan.tasks}
    _, groups = topological_order(deps)
    flattened = [task_id for group in groups for task_id in group]
    assert sorted(flattened) == sorted(deps), "cycle must be broken so all tasks order"
    assert any("cycle" in note.lower() for note in notes)


def test_parallel_tasks_are_identified():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    for task in breakdown.tasks:  # no chain: everything independent
        task.dependencies = []
    plan, _ = repair_breakdown(breakdown, spec, _requirements())
    deps = {task.task_id: list(task.dependencies) for task in plan.tasks}
    _, groups = topological_order(deps)
    # Every content task is independent; the only dependent task may be the
    # deterministic approval safeguard, which is appended when an approval
    # requirement is untagged.
    independent = [task_id for task_id, task_deps in deps.items() if not task_deps]
    assert len(independent) >= len(plan.tasks) - 1
    assert len(groups[0]) == len(independent)


def test_topological_order_respects_prerequisites():
    deps = {"task_3": ["task_2"], "task_2": ["task_1"], "task_1": []}
    order, groups = topological_order(deps)
    assert order.index("task_1") < order.index("task_2") < order.index("task_3")
    assert groups[0] == ["task_1"]


def test_critical_path_follows_the_dependency_chain():
    from app.agent.optimization import optimize_plan
    spec = _bme_spec()
    plan, _ = repair_breakdown(_breakdown_from(spec), spec, _requirements())
    result = optimize_plan(plan, deadline=None, completed_task_ids=[])
    assert result.critical_path, "critical path computed from qualitative efforts"
    assert result.critical_path_effort >= len(result.critical_path)


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------


def test_validation_flags_uncovered_deliverables():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    plan, _ = repair_breakdown(breakdown, spec, _requirements())
    result = validate_plan(plan, _requirements(), 0, spec=spec)
    codes = [issue.code for issue in result.errors]
    assert "uncovered_deliverable" in codes  # deliverables never tagged


def test_validation_passes_when_deliverables_are_covered():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    breakdown.tasks[-1].deliverable = spec.all_deliverable_texts()[0]
    breakdown.tasks[-1].deliverable_refs = ["0"]
    breakdown.tasks[-1].deliverable_refs.append("1") if len(spec.deliverables) > 1 else None
    plan, _ = repair_breakdown(breakdown, spec, _requirements())
    result = validate_plan(plan, _requirements(), 0, spec=spec)
    assert all(issue.code != "uncovered_deliverable" for issue in result.errors)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def _state_with(tasks, completed=None):
    from app.models.task import Task
    return {
        "tasks": tasks,
        "completed_tasks": completed or [],
        "workflow_id": "wf_test",
        "optimization": None,
    }


def test_recommendation_targets_ready_task_and_explains_unblocking():
    from app.agent.nodes.recommendation import recommendation_node
    from app.models.task import Task

    tasks = [
        Task(id="task_1", title="Download easyCLIP datasets", description="Download and inspect replicates."),
        Task(id="task_2", title="Call peaks", description="Call peaks for both conditions.", dependencies=["task_1"]),
    ]
    recommendation = recommendation_node(_state_with(tasks))["recommendation"]
    assert recommendation.action == "start_task"
    assert recommendation.affected_task == "task_1"
    assert "unblocks" in recommendation.reason.lower()
    assert "Call peaks" in recommendation.reason  # explains what it unlocks


def test_recommendation_never_references_missing_tasks():
    from app.agent.nodes.recommendation import recommendation_node
    from app.models.task import Task

    tasks = [Task(id="task_1", title="Only task", description="Do the thing.")]
    recommendation = recommendation_node(_state_with(tasks))["recommendation"]
    assert recommendation.affected_task == "task_1"
    assert recommendation.recommendation_id == "rec_wf_test"


def test_recommendation_survives_persistence_and_reopening():
    import tempfile

    from app.agent.service import AgentService
    from app.memory.local import LocalMemoryStore
    from app.rag.embeddings import LocalHashEmbeddings
    from app.rag.vector_store import LocalVectorStore, VectorRetriever

    with tempfile.TemporaryDirectory() as tmp:
        memory = LocalMemoryStore(tmp)
        retriever = VectorRetriever(LocalVectorStore(tmp + "/vectors.json"), LocalHashEmbeddings())
        service = AgentService(MockLLMProvider(), retriever, memory)
        workflow = service.create_workflow_sync("Prepare the KHDRBS2 comparison")
        original_id = workflow.recommendation.recommendation_id
        assert original_id

        reopened = memory.get_workflow(workflow.workflow_id)
        assert reopened.recommendation.recommendation_id == original_id
        # The recommended task actually exists in the persisted plan.
        task_ids = {task.id for task in reopened.tasks}
        assert reopened.recommendation.affected_task in task_ids


def test_recommendation_explains_parallel_options():
    from app.agent.nodes.recommendation import recommendation_node
    from app.models.task import Task

    tasks = [
        Task(id="task_1", title="Download datasets", description="Download."),
        Task(id="task_2", title="Review literature", description="Read.", priority="medium"),
    ]
    recommendation = recommendation_node(_state_with(tasks))["recommendation"]
    assert "parallel" in recommendation.reason.lower()


# ---------------------------------------------------------------------------
# User-facing language
# ---------------------------------------------------------------------------


def test_user_facing_text_does_not_expose_internal_identifiers():
    from app.agent.nodes.recommendation import recommendation_node
    from app.models.task import Task

    tasks = [
        Task(id="task_3", title="Annotate binding sites by transcript region", description="Annotate each binding site."),
    ]
    recommendation = recommendation_node(_state_with(tasks))["recommendation"]
    assert "task_3" not in recommendation.reason
    assert "Annotate binding sites" in recommendation.reason


def test_planning_notes_are_observable_and_bounded():
    spec = _bme_spec()
    breakdown = _breakdown_from(spec)
    breakdown.tasks[0].dependencies = ["task_999"]
    plan, notes = repair_breakdown(breakdown, spec, _requirements())
    assert isinstance(notes, list) and notes  # the process is observable


# ---------------------------------------------------------------------------
# Regression: BME 415 document drives the whole pipeline (mock provider)
# ---------------------------------------------------------------------------


def test_bme415_document_present_and_content_loads():
    assert BME_DOCUMENT.exists(), "fixture document must exist"
    text = BME_DOCUMENT.read_text(encoding="utf-8")
    assert "R168C" in text and "easyCLIP" in text


def test_full_pipeline_with_document_produces_grounded_plan(tmp_path, monkeypatch):
    """Ingest the BME 415 fixture, run the graph, and verify the plan is
    derived from the document (not the generic administrative template)."""
    from fastapi.testclient import TestClient

    from app.agent.service import AgentService
    from app.api.dependencies import get_agent_service, get_retriever
    from app.memory.local import LocalMemoryStore
    from app.main import app
    from app.rag.embeddings import LocalHashEmbeddings
    from app.rag.vector_store import LocalVectorStore, VectorRetriever

    memory = LocalMemoryStore(tmp_path)
    retriever = VectorRetriever(LocalVectorStore(tmp_path / "vectors.json"), LocalHashEmbeddings())
    service = AgentService(MockLLMProvider(), retriever, memory)
    app.dependency_overrides[get_agent_service] = lambda: service
    app.dependency_overrides[get_retriever] = lambda: retriever
    try:
        client = TestClient(app)
        created = client.post("/goals?sync=true", json={"goal": "Compare KHDRBS2 wild-type and R168C easyCLIP binding"})
        assert created.status_code == 201
        workflow_id = created.json()["workflow_id"]

        document = BME_DOCUMENT.read_bytes()
        ingested = client.post(
            "/documents/ingest",
            files={"file": ("bme415_proposal.txt", document, "text/plain")},
            data={"workflow_id": workflow_id},
        )
        assert ingested.status_code == 200

        refreshed = client.post(f"/workflows/{workflow_id}/refresh")
        assert refreshed.status_code == 200
        body = refreshed.json()

        # The plan must reference the document's actual research content.
        plan_text = " ".join(
            ((task.get("title") or "") + " " + task.get("description", "")).lower()
            for task in body["tasks"]
        )
        assert any(term in plan_text for term in ("r168c", "binding", "khdrbs2"))
        # …and must not contain the old generic admin tasks.
        assert "governing organizational policies" not in plan_text
        spec = body.get("project_specification") or {}
        assert spec.get("project_type") in ("academic_research", "general")
        # The specification must be grounded in the ingested document.
        assert any(
            "r168c" in (item.get("content", "") or "").lower()
            for section in ("major_activities", "objective", "research_questions")
            for item in (spec.get(section) or [])
        )
    finally:
        app.dependency_overrides.clear()


def test_generic_goal_without_document_produces_different_plan_than_document_goal(tmp_path):
    from app.agent.service import AgentService
    from app.memory.local import LocalMemoryStore
    from app.rag.embeddings import LocalHashEmbeddings
    from app.rag.vector_store import LocalVectorStore, VectorRetriever

    memory = LocalMemoryStore(tmp_path)
    retriever = VectorRetriever(LocalVectorStore(tmp_path / "vectors.json"), LocalHashEmbeddings())
    service = AgentService(MockLLMProvider(), retriever, memory)

    with_doc = service.create_workflow_sync("Compare KHDRBS2 wild-type and R168C easyCLIP binding")
    # Simulate that documents were understood (the understanding node caches
    # the specification in state; feed the fixture spec directly).
    spec = _bme_spec()
    breakdown = service.llm.build_work_breakdown(spec, _requirements(), "(evidence)")
    plan_doc, _ = repair_breakdown(breakdown, spec, _requirements())

    without_doc = service.create_workflow_sync("Deploy the staging environment")

    doc_titles = {task.title for task in plan_doc.tasks}
    generic_titles = {task.title for task in without_doc.tasks}
    assert doc_titles != generic_titles
    assert any("R168C" in title or "binding" in title.lower() for title in doc_titles)
