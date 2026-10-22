from pathlib import Path

import pytest

from app.models.task import Task
from app.models.workflow import WorkflowState
from app.workspace import Conflict, WorkspaceError, WorkspaceStore, transition_task


def workflow() -> WorkflowState:
    return WorkflowState(workflow_id="wf_test", original_goal="Test", tasks=[
        Task(id="one", description="First"),
        Task(id="two", description="Second", dependencies=["one"]),
    ])


def test_persists_isolates_and_reopens(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite3")
    first = store.ensure(workflow())
    second = store.ensure(WorkflowState(workflow_id="wf_other", original_goal="Other"))
    assert first.workflow_id != second.workflow_id
    reopened = WorkspaceStore(tmp_path / "workspace.sqlite3").get("wf_test")
    assert reopened.tasks[0].readiness == "ready"
    assert reopened.tasks[1].readiness == "waiting"


def test_transition_version_and_dependency_rules(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite3")
    current = store.ensure(workflow())
    transition_task(current, "one", "in_progress")
    current = store.save(current, 1, "task_status_changed", "one")
    transition_task(current, "one", "completed")
    current = store.save(current, 2, "task_status_changed", "one")
    assert current.tasks[1].status == "ready"
    with pytest.raises(WorkspaceError):
        transition_task(current, "two", "completed")
    with pytest.raises(Conflict):
        store.save(current, 1, "task_status_changed")


def test_rejects_cycle_and_records_events(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite3")
    current = store.ensure(workflow())
    with pytest.raises(ValueError):
        store.revise(current, 1, [Task(id="a", description="a", dependencies=["b"]), Task(id="b", description="b", dependencies=["a"])], "cycle")
    assert store.events("wf_test")[0].event_type == "workflow_synced"
