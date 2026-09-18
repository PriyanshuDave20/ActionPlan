from typing import Literal

from pydantic import BaseModel, Field

from app.models.evidence import Evidence


class Requirement(BaseModel):
    id: str = Field(min_length=1)
    category: Literal["policy", "process", "approval", "evidence", "definition"] = "definition"
    text: str = Field(min_length=1)
    rationale: str | None = None
    relevant_tasks: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    covered: bool = False


class RequirementExtraction(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)