from datetime import date

from app.agent.graph import should_revise
from app.agent.nodes.plan_validation import plan_failed_node, revise_plan_node
from app.agent.optimization import optimize_plan
from app.agent.validation import MAX_PLAN_REVISIONS, validate_plan
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
    plan.tasks[1].required_approvals = ["decision_maker"]
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


# --- Plan validation regression tests ---


def test_valid_plan_reaches_execution():
    """A fully valid plan should route to execute_plan, not revision or failure."""
    plan = _plan_tasks(
        [
            ("task_1", "req_1", "small", []),
            ("task_2", "req_2", "medium", ["task_1"]),
        ]
    )
    plan.tasks[1].required_approvals = ["decision_maker"]
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="process", text="a"),
            Requirement(id="req_2", category="approval", text="b"),
        ],
        revision_count=0,
    )
    assert result.valid is True
    assert should_revise({"plan_validation": result, "plan_revision_count": 0}) == "execute_plan"


def test_plan_missing_approval_task_is_invalid():
    """An approval-category requirement without an approval task is invalid."""
    plan = _plan_tasks([("task_1", "req_1", "small", [])])
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=0,
    )
    assert result.valid is False
    assert any(issue.code == "missing_approval_task" for issue in result.errors)
    assert "req_1" in result.missing_approvals


def test_plan_with_uncovered_requirements_is_invalid():
    """Requirements not covered by any task make the plan invalid."""
    plan = _plan_tasks([("task_1", "req_1", "small", [])])
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="process", text="covered"),
            Requirement(id="req_2", category="policy", text="uncovered"),
        ],
        revision_count=0,
    )
    assert result.valid is False
    assert result.uncovered_requirements == ["req_2"]


def test_revision_that_fixes_errors_passes_revalidation():
    """A revision that adds missing approval coverage should revalidate as valid."""
    plan = _plan_tasks(
        [
            ("task_1", "req_1", "small", []),
        ]
    )
    result_before = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=0,
    )
    assert result_before.valid is False
    assert "req_1" in result_before.missing_approvals

    # Revise: add an approval task for req_1
    plan.tasks.append(
        CandidateTask(
            task_id="task_2",
            description="Obtain approval for req_1",
            requirement_id="req_1",
            effort="small",
            dependencies=[],
            required_approvals=["decision_maker"],
        )
    )
    result_after = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=1,
    )
    assert result_after.valid is True


def test_revision_that_does_not_fix_errors_stays_invalid():
    """A revision that does not address validation errors stays invalid."""
    plan = _plan_tasks(
        [
            ("task_1", "req_1", "small", []),
        ]
    )
    result_before = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=0,
    )
    assert result_before.valid is False

    # Revise: add a task that does NOT cover the approval requirement
    plan.tasks.append(
        CandidateTask(
            task_id="task_2",
            description="Unrelated work",
            requirement_id=None,
            effort="small",
            dependencies=[],
        )
    )
    result_after = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=1,
    )
    assert result_after.valid is False
    assert "req_1" in result_after.missing_approvals


def test_exhausted_revision_budget_routes_to_plan_failed():
    """When the revision budget is exhausted, should_revise returns plan_failed,
    never execute_plan, for an invalid plan."""
    plan = _plan_tasks([("task_1", "req_1", "small", [])])
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=MAX_PLAN_REVISIONS,
    )
    assert result.valid is False
    assert should_revise({"plan_validation": result, "plan_revision_count": MAX_PLAN_REVISIONS}) == "plan_failed"


def test_no_invalid_plan_reaches_execute_plan():
    """Confirm should_revise never returns execute_plan for an invalid plan,
    regardless of revision count."""
    plan = _plan_tasks([("task_1", "req_1", "small", [])])
    result = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=0,
    )
    assert result.valid is False
    for count in range(MAX_PLAN_REVISIONS + 1):
        decision = should_revise(
            {"plan_validation": result, "plan_revision_count": count}
        )
        assert decision != "execute_plan", (
            f"Invalid plan should not execute at revision count {count}"
        )


def test_plan_failed_node_records_failure():
    """plan_failed_node records an explicit failure state instead of executing."""
    plan = _plan_tasks([("task_1", "req_1", "small", [])])
    validation = validate_plan(
        plan,
        [
            Requirement(id="req_1", category="approval", text="needs approval"),
        ],
        revision_count=MAX_PLAN_REVISIONS,
    )
    state = {
        "plan_validation": validation,
        "plan_revision_count": MAX_PLAN_REVISIONS,
        "execution_metadata": {},
    }
    updated = plan_failed_node(state)
    assert updated["execution_metadata"]["plan_failed"] is True
    assert updated["execution_metadata"]["validation"] == "failed"
    assert "failure_reason" in updated["execution_metadata"]