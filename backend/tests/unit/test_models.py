import pytest
from pydantic import ValidationError

from app.models.goal import GoalInput
from app.models.task import Task, TaskPlan


def test_empty_goal_rejected():
    with pytest.raises(ValidationError):
        GoalInput(goal="")


def test_task_ids_and_dependencies_are_validated():
    plan = TaskPlan(tasks=[Task(id="a", description="A"), Task(id="b", description="B", dependencies=["a"])])
    assert [task.id for task in plan.tasks] == ["a", "b"]
    with pytest.raises(ValueError, match="cycle"):
        TaskPlan(tasks=[Task(id="a", description="A", dependencies=["b"]), Task(id="b", description="B", dependencies=["a"])])


def test_unknown_dependency_rejected():
    with pytest.raises(ValueError, match="unknown dependencies"):
        TaskPlan(tasks=[Task(id="a", description="A", dependencies=["missing"])])
