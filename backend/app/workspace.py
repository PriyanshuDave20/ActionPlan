"""Transactional V2 workspace state. SQLite is deliberately separate from RAG."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.task import Task, TaskPlan
from app.models.workflow import Recommendation, WorkflowState
from app.models.workspace import WorkflowEvent


class WorkspaceError(ValueError):
    status_code = 400


class NotFound(WorkspaceError):
    status_code = 404


class Conflict(WorkspaceError):
    status_code = 409


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceStore:
    """Small migration-free SQLite repository; schema is created idempotently."""
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init(self) -> None:
        with self._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS workspace_workflows (
              workflow_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, version INTEGER NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspace_tasks (
              workflow_id TEXT NOT NULL, task_id TEXT NOT NULL, task_json TEXT NOT NULL,
              PRIMARY KEY (workflow_id, task_id),
              FOREIGN KEY(workflow_id) REFERENCES workspace_workflows(workflow_id)
            );
            CREATE TABLE IF NOT EXISTS workflow_events (
              event_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, event_type TEXT NOT NULL,
              occurred_at TEXT NOT NULL, entity_id TEXT, details_json TEXT NOT NULL,
              actor TEXT NOT NULL, version INTEGER
            );
            CREATE INDEX IF NOT EXISTS workflow_events_by_workflow ON workflow_events(workflow_id, occurred_at);
            CREATE TABLE IF NOT EXISTS plan_revisions (
              revision_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, version INTEGER NOT NULL,
              tasks_json TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendations (
              recommendation_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, recommendation_json TEXT NOT NULL,
              version INTEGER NOT NULL, created_at TEXT NOT NULL, decided_at TEXT
            );
            CREATE TABLE IF NOT EXISTS idempotency_keys (
              idempotency_key TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """)

    def ensure(self, workflow: WorkflowState) -> WorkflowState:
        with self._connection() as db:
            row = db.execute("SELECT state_json FROM workspace_workflows WHERE workflow_id=?", (workflow.workflow_id,)).fetchone()
            if row:
                return WorkflowState.model_validate_json(row["state_json"])
            self._write(db, workflow, event_type="workflow_created", actor="system")
            return workflow

    def get_by_idempotency_key(self, idempotency_key: str) -> WorkflowState | None:
        with self._connection() as db:
            row = db.execute("SELECT workflow_id FROM idempotency_keys WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if not row:
                return None
            return self.get(row["workflow_id"])

    def set_idempotency_key(self, idempotency_key: str, workflow_id: str) -> None:
        with self._connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO idempotency_keys (idempotency_key, workflow_id, created_at) VALUES (?, ?, ?)",
                (idempotency_key, workflow_id, _now().isoformat())
            )

    def get(self, workflow_id: str) -> WorkflowState:
        with self._connection() as db:
            row = db.execute("SELECT state_json FROM workspace_workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
        if not row:
            raise NotFound(f"Workflow {workflow_id} not found.")
        return WorkflowState.model_validate_json(row["state_json"])

    def save(self, workflow: WorkflowState, expected_version: int, event_type: str, entity_id: str | None = None, details: dict | None = None, actor: str = "user") -> WorkflowState:
        with self._connection() as db:
            current = db.execute("SELECT version FROM workspace_workflows WHERE workflow_id=?", (workflow.workflow_id,)).fetchone()
            if not current:
                raise NotFound(f"Workflow {workflow.workflow_id} not found.")
            if current["version"] != expected_version:
                raise Conflict("This workflow changed. Reload it before making another update.")
            workflow.version = expected_version + 1
            workflow.updated_at = _now()
            self._write(db, workflow, event_type, entity_id, details or {}, actor)
        return workflow

    def _write(self, db: sqlite3.Connection, workflow: WorkflowState, event_type: str, entity_id: str | None = None, details: dict | None = None, actor: str = "user") -> None:
        workflow.tasks = recompute_readiness(workflow.tasks)
        state_json = workflow.model_dump_json()
        db.execute("INSERT INTO workspace_workflows(workflow_id,state_json,version,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(workflow_id) DO UPDATE SET state_json=excluded.state_json,version=excluded.version,updated_at=excluded.updated_at", (workflow.workflow_id, state_json, workflow.version, workflow.created_at.isoformat(), workflow.updated_at.isoformat()))
        db.execute("DELETE FROM workspace_tasks WHERE workflow_id=?", (workflow.workflow_id,))
        db.executemany("INSERT INTO workspace_tasks(workflow_id,task_id,task_json) VALUES(?,?,?)", [(workflow.workflow_id, t.id, t.model_dump_json()) for t in workflow.tasks])
        event = WorkflowEvent(event_id=uuid4().hex, workflow_id=workflow.workflow_id, event_type=event_type, occurred_at=_now(), entity_id=entity_id, details=details or {}, actor=actor, version=workflow.version)
        db.execute("INSERT INTO workflow_events VALUES(?,?,?,?,?,?,?,?)", (event.event_id,event.workflow_id,event.event_type,event.occurred_at.isoformat(),event.entity_id,json.dumps(event.details),event.actor,event.version))
        if workflow.recommendation:
            recommendation = workflow.recommendation
            if not recommendation.recommendation_id:
                recommendation.recommendation_id = uuid4().hex
            recommendation.workflow_id = workflow.workflow_id
            db.execute("INSERT OR REPLACE INTO recommendations VALUES(?,?,?,?,?,?)", (recommendation.recommendation_id,workflow.workflow_id,recommendation.model_dump_json(),workflow.version,recommendation.created_at.isoformat(),recommendation.decided_at.isoformat() if recommendation.decided_at else None))

    def events(self, workflow_id: str) -> list[WorkflowEvent]:
        with self._connection() as db:
            rows = db.execute("SELECT * FROM workflow_events WHERE workflow_id=? ORDER BY occurred_at DESC", (workflow_id,)).fetchall()
        return [WorkflowEvent(event_id=r["event_id"], workflow_id=r["workflow_id"], event_type=r["event_type"], occurred_at=datetime.fromisoformat(r["occurred_at"]), entity_id=r["entity_id"], details=json.loads(r["details_json"]), actor=r["actor"], version=r["version"]) for r in rows]

    def revise(self, workflow: WorkflowState, expected_version: int, tasks: list[Task], reason: str | None) -> WorkflowState:
        TaskPlan.validate_tasks(tasks)
        with self._connection() as db:
            current = db.execute("SELECT version FROM workspace_workflows WHERE workflow_id=?", (workflow.workflow_id,)).fetchone()
            if not current: raise NotFound(f"Workflow {workflow.workflow_id} not found.")
            if current["version"] != expected_version: raise Conflict("This workflow changed. Reload it before making another update.")
            db.execute("INSERT INTO plan_revisions VALUES(?,?,?,?,?,?)", (uuid4().hex,workflow.workflow_id,expected_version,json.dumps([task.model_dump(mode="json") for task in workflow.tasks]),reason,_now().isoformat()))
            workflow.tasks = tasks
            workflow.plan_revision_count += 1
            return self.save_in_transaction(db, workflow, expected_version, "plan_revised", details={"reason": reason or "", "task_count": len(tasks)})

    def save_in_transaction(self, db, workflow, expected, event_type, entity_id=None, details=None):
        workflow.version = expected + 1; workflow.updated_at = _now()
        self._write(db, workflow, event_type, entity_id, details or {})
        return workflow


def recompute_readiness(tasks: list[Task]) -> list[Task]:
    TaskPlan.validate_tasks(tasks)
    by_id = {task.id: task for task in tasks}
    for task in tasks:
        if task.status == "completed": task.readiness = "complete"
        elif task.status == "cancelled": task.readiness = "cancelled"
        elif task.status == "blocked": task.readiness = "blocked"
        elif all(by_id[d].status == "completed" for d in task.dependencies):
            task.readiness = "ready"
            if task.status == "pending": task.status = "ready"
        else:
            task.readiness = "waiting"
            if task.status == "ready": task.status = "pending"
    return tasks


def transition_task(workflow: WorkflowState, task_id: str, target: str) -> Task:
    task = next((item for item in workflow.tasks if item.id == task_id), None)
    if not task: raise NotFound(f"Task {task_id} not found.")
    recompute_readiness(workflow.tasks)
    allowed = {"pending":{"ready","blocked","cancelled"},"ready":{"in_progress","blocked","cancelled","pending"},"in_progress":{"completed","blocked","cancelled"},"blocked":{"pending","ready","cancelled"},"completed":set(),"cancelled":set()}
    if target not in allowed[task.status]: raise WorkspaceError(f"Cannot transition task from {task.status} to {target}.")
    if target in {"ready","in_progress"} and task.readiness != "ready": raise WorkspaceError("Dependencies must be completed before this task can start.")
    task.status = target
    recompute_readiness(workflow.tasks)
    workflow.completed_tasks = [t.id for t in workflow.tasks if t.status == "completed"]
    return task
