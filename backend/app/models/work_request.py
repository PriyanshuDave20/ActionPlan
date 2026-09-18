from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Person(BaseModel):
    name: str
    role: str = "contributor"


class WorkRequestInput(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    people_involved: list[Person] = Field(default_factory=list)
    deadline: date | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    current_status: str | None = None
    constraints: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class WorkRequest(BaseModel):
    goal: str
    people: list[Person] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    deadline: date | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    current_status: str | None = None
    constraints: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


def compile_work_request(payload: WorkRequestInput) -> WorkRequest:
    roles = sorted({person.role for person in payload.people_involved if person.role})
    return WorkRequest(
        goal=payload.goal,
        people=payload.people_involved,
        roles=roles,
        deadline=payload.deadline,
        priority=payload.priority,
        current_status=payload.current_status,
        constraints=payload.constraints,
        resources=payload.resources,
        success_criteria=payload.success_criteria,
    )