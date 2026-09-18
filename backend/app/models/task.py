from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.evidence import Evidence


class Task(BaseModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    effort: Literal["small", "medium", "large", "high"] = "small"
    role: str | None = None
    owner: str | None = None
    mandatory: bool = True
    required_information: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    procedure_sources: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class TaskPlan(BaseModel):
    tasks: list[Task] = Field(default_factory=list)

    @classmethod
    def validate_tasks(cls, tasks: list[Task]) -> list[Task]:
        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task IDs must be unique")
        known = set(ids)
        for task in tasks:
            missing = set(task.dependencies) - known
            if missing:
                raise ValueError(f"task {task.id} has unknown dependencies: {sorted(missing)}")
        graph = {task.id: task.dependencies for task in tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("task dependencies contain a cycle")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in graph[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in graph:
            visit(task_id)
        return tasks

    @field_validator("tasks")
    @classmethod
    def validate_dependencies(cls, tasks: list[Task]) -> list[Task]:
        return cls.validate_tasks(tasks)