import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.workflow import WorkflowState, WorkflowSummary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalMemoryStore:
    """JSON-file memory store for offline development and tests."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.workflows_dir = self.data_dir / "workflows"
        self.long_term_file = self.data_dir / "long_term_memory.json"
        self._index_file = self.data_dir / "workflows" / "_index.json"
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

    # -- workflows ------------------------------------------------

    def save_workflow(self, workflow: WorkflowState) -> None:
        payload = workflow.model_dump(mode="json")
        workflow_file = self.workflows_dir / f"{workflow.workflow_id}.json"
        with workflow_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        self._update_index(workflow.workflow_id, workflow.updated_at.isoformat())

    def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        workflow_file = self.workflows_dir / f"{workflow_id}.json"
        if not workflow_file.exists():
            return None
        with workflow_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return WorkflowState.model_validate(payload)

    def list_workflows(self) -> list[WorkflowState]:
        entries = []
        for workflow_file in self.workflows_dir.glob("*.json"):
            if workflow_file.name == "_index.json":
                continue
            with workflow_file.open("r", encoding="utf-8") as handle:
                try:
                    payload = json.load(handle)
                except json.JSONDecodeError:
                    continue
            entries.append(WorkflowState.model_validate(payload))
        entries.sort(key=lambda workflow: workflow.updated_at, reverse=True)
        return entries

    def summarize(self) -> WorkflowSummary | None:
        workflows = self.list_workflows()
        if not workflows:
            return None
        latest = workflows[0]
        return WorkflowSummary(
            workflow_id=latest.workflow_id,
            goal=latest.original_goal,
            updated_at=latest.updated_at,
            deadline=latest.work_request.deadline if latest.work_request else None,
            priority=(latest.work_request.priority or "medium") if latest.work_request else "medium",
            total_tasks=len(latest.tasks),
            completed_tasks=len([
                task for task in latest.tasks if task.status == "completed"
            ]),
            blocker_count=len(latest.detected_blockers),
            recommendation_action=(
                latest.recommendation.action if latest.recommendation else None
            ),
        )

    def _update_index(self, workflow_id: str, updated_at: str) -> None:
        index: dict[str, str] = {}
        if self._index_file.exists():
            try:
                with self._index_file.open("r", encoding="utf-8") as handle:
                    index = json.load(handle)
            except (json.JSONDecodeError, OSError):
                index = {}
        index[workflow_id] = updated_at
        with self._index_file.open("w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=2)

    # -- long-term memory -----------------------------------------

    def set_long_term_memory(self, key: str, value: str) -> None:
        memory = self._load_long_term()
        memory[key] = {"value": value, "updated_at": _now()}
        with self.long_term_file.open("w", encoding="utf-8") as handle:
            json.dump(memory, handle, indent=2)

    def get_long_term_memory(self, key: str) -> str | None:
        return self._load_long_term().get(key, {}).get("value")

    def _load_long_term(self) -> dict:
        if not self.long_term_file.exists():
            return {}
        try:
            with self.long_term_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}