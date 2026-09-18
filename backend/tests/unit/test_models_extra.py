import pytest
from pydantic import ValidationError

from app.models.evidence import Evidence
from app.models.frames import ObjectiveAnalysis, ProcedureExtraction
from app.models.optimization import OptimizationResult, TargetedEvidence
from app.models.plan import CandidatePlan, CandidateTask, PlanValidationResult, ValidationIssue
from app.models.procedure import Procedure, ProcedureOption, ProcedureStep
from app.models.requirement import Requirement, RequirementExtraction


def test_evidence_document_type_alias():
    evidence = Evidence(content="install", doc_type="policy.doc")
    assert evidence.document_type == "policy.doc"


def test_evidence_defaults():
    evidence = Evidence(content="Install the badge readers", source="onboarding.pdf", page=2)
    assert evidence.page == 2
    assert evidence.source == "onboarding.pdf"


def test_procedure_steps_default_required_information():
    procedure = Procedure(
        id="prc_1",
        name="Buddy onboarding",
        steps=[
            ProcedureStep(
                order=1,
                action="Assign a buddy",
            )
        ],
    )
    assert procedure.steps[0].required_information == []
    assert procedure.steps[0].optional is False


def test_requirement_extraction_defaults_empty():
    extraction = RequirementExtraction()
    assert extraction.requirements == []


def test_targeted_evidence_holds_evidence():
    targeted = TargetedEvidence(
        requirement_id="req_1",
        query="security review",
        evidence=[Evidence(content="run a review")],
    )
    assert targeted.evidence[0].content == "run a review"


def test_validation_issue_optional_task_id():
    issue = ValidationIssue(code="unknown_dependency", message="bad dep")
    assert issue.task_id is None


def test_plan_validation_defaults_valid():
    result = PlanValidationResult()
    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_invalid_priority_is_not_required_field():
    candidate = CandidatePlan(rationale="x", tasks=[CandidateTask(task_id="a", description="A")])
    assert candidate.tasks[0].effort == "small"


def test_high_effort_literal_accepted():
    task = CandidateTask(task_id="h", description="H", effort="high")
    assert task.effort == "high"


def test_bad_effort_literal_rejected():
    with pytest.raises(ValidationError):
        CandidateTask(task_id="x", description="X", effort="massive")


def test_optimization_result_default_values():
    result = OptimizationResult(summary="ok")
    assert result.critical_path == []
    assert result.parallel_chains == []
    assert result.days_until_deadline is None


def test_works_request_success_criteria_in_objective():
    objective = ObjectiveAnalysis(objective="Do the thing", success_criteria=["c1"])
    assert objective.success_criteria == ["c1"]