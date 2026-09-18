from typing import Protocol

from app.models.workflow import WorkflowState, WorkflowSummary


class MemoryInterface(Protocol):
    def save_workflow(self, workflow: WorkflowState) -> None:
        ...

    def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        ...

    def list_workflows(self) -> list[WorkflowState]:
        ...

    def set_long_term_memory(self, key: str, value: str) -> None:
        ...

    def get_long_term_memory(self, key: str) -> str | None:
        ...

    def summarize(self) -> WorkflowSummary | None:
        ...