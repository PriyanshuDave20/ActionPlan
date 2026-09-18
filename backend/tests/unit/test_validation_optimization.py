from datetime import date

from app.agent.optimization import optimize_plan
from app.agent.validation import validate_plan
from app.models.plan import CandidatePlan, CandidateTask
from app.models.requirement import Requirement


def _plan_tasks(tasks):
    return CandidatePlan(
        rationale="test",
        tasks=[
            CandidateTask(
                task_id=task_id,
                description=f"Task {task_id}",
                requirement_id=requirement_id,
                effort=effort,
                dependencies=dependencies,
            )
            for task_id, requirement_id, effort, dependencies in tasks
        ],
    )


def test_valid_plan_passes_validation():
    plan = _plan_tasks(
        [
            ("task_1", "req_1", "small", []),
            ("task_2", "req_2", "medium", ["task_1"]),
        ]
    )
    plan.tasks[1].description = "Prepare and obtain approval for the change"
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="process", text="a"),
            Requirement(id="req_2", category="approval", text="b"),
        ],
        revision_count=0,
    )
    assert result.valid is True
    assert result.uncovered_requirements == []
    assert result.invalid_dependencies == []


def test_unknown_dependency_detected():
    plan = _plan_tasks([("task_1", "req_1", "small", ["ghost"])])
    result = validate_plan(plan, [Requirement(id="req_1", category="process", text="a")], 0)
    assert result.valid is False
    assert result.invalid_dependencies == ["task_1"]


def test_dependency_cycle_detected():
    plan = _plan_tasks(
        [
            ("task_1", "req_1", "small", ["task_2"]),
            ("task_2", "req_2", "small", ["task_1"]),
        ]
    )
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="process", text="a"),
            Requirement(id="req_2", category="process", text="b"),
        ],
        0,
    )
    assert result.valid is False
    assert any(issue.code == "dependency_cycle" for issue in result.errors)


def test_uncovered_requirement_reported():
    plan = _plan_tasks([("task_1", "req_1", "small", [])])
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="process", text="a"),
            Requirement(id="req_2", category="policy", text="b"),
        ],
        0,
    )
    assert result.valid is False
    assert result.uncovered_requirements == ["req_2"]


def test_revision_count_tracked():
    plan = _plan_tasks([("task_1", "req_1", "small", [])])
    result = validate_plan(plan, [Requirement(id="req_1", category="process", text="a")], 2)
    assert result.revision_count == 2


def test_optimization_critical_path_and_deadline():
    plan = _plan_tasks(
        [
            ("task_1", "req_1", "small", []),
            ("task_2", "req_2", "large", ["task_1"]),
            ("task_3", "req_3", "small", ["task_2"]),
        ]
    )
    result = optimize_plan(plan, deadline=date(2030, 1, 1), completed_task_ids=[])
    assert result.critical_path == ["task_1", "task_2", "task_3"]
    assert result.critical_path_effort >= 5
    assert result.deadline_feasible is True


def test_optimization_parallel_chains_detected():
    plan = _plan_tasks(
        [
            ("task_1", "req_1", "small", []),
            ("task_2", "req_2", "small", []),
            ("task_3", "req_3", "small", ["task_1"]),
        ]
    )
    result = optimize_plan(plan, deadline=None, completed_task_ids=[])
    assert result.days_until_deadline is None
    assert result.deadline_feasible is None
    assert len(result.critical_path) >= 2