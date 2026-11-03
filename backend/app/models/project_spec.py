"""Structured document understanding models for document-grounded planning.

Every extracted fact carries its evidence (document, page, passage), a
confidence, and whether it was explicitly stated in a document or inferred.
Missing information is represented as an entry in ``missing_information``
— never fabricated.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectType = Literal[
    "academic_research",
    "software_development",
    "business_initiative",
    "operational_improvement",
    "event_planning",
    "product_development",
    "general",
]

# Supported planning methodologies. The classifier picks one; the planner
# adapts the pattern to the actual documents rather than applying a template.
PROJECT_TYPES: tuple[str, ...] = (
    "academic_research",
    "software_development",
    "business_initiative",
    "operational_improvement",
    "event_planning",
    "product_development",
    "general",
)


class EvidenceRef(BaseModel):
    """Pointer to the passage a fact was extracted from."""

    document: str = ""          # document identifier / filename
    page: int | None = None
    section: str | None = None  # section heading when known
    passage: str = ""           # supporting quote or retrieval reference


class SpecItem(BaseModel):
    """A single extracted fact with provenance."""

    content: str
    source: EvidenceRef = Field(default_factory=EvidenceRef)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    kind: Literal["explicit", "inference"] = "explicit"


def _items() -> list[SpecItem]:
    return []


class ProjectSpecification(BaseModel):
    """Structured project specification extracted from project documents."""

    title: str = ""
    project_type: ProjectType = "general"
    objective: list[SpecItem] = Field(default_factory=_items)
    research_questions: list[SpecItem] = Field(default_factory=_items)
    scope: list[SpecItem] = Field(default_factory=_items)
    methodology: list[SpecItem] = Field(default_factory=_items)
    major_activities: list[SpecItem] = Field(default_factory=_items)
    deliverables: list[SpecItem] = Field(default_factory=_items)
    milestones: list[SpecItem] = Field(default_factory=_items)
    constraints: list[SpecItem] = Field(default_factory=_items)
    resources: list[SpecItem] = Field(default_factory=_items)
    people: list[SpecItem] = Field(default_factory=_items)
    deadlines: list[SpecItem] = Field(default_factory=_items)
    evaluation_criteria: list[SpecItem] = Field(default_factory=_items)
    dependencies: list[SpecItem] = Field(default_factory=_items)
    risks: list[SpecItem] = Field(default_factory=_items)
    # Facts the documents do NOT specify. Never filled with invented values.
    missing_information: list[str] = Field(default_factory=list)
    # Deterministic retrieval probes derived from the goal, used to gather
    # broader document coverage than a single top-k query.
    search_queries: list[str] = Field(default_factory=list)

    def has_document_evidence(self) -> bool:
        """True when any section carries an explicit, document-sourced fact."""
        for field_name in (
            "objective", "research_questions", "scope", "methodology",
            "major_activities", "deliverables", "milestones", "constraints",
            "resources", "people", "deadlines", "evaluation_criteria",
            "dependencies", "risks",
        ):
            for item in getattr(self, field_name):
                if item.kind == "explicit" and item.source.document:
                    return True
        return False

    def all_deliverable_texts(self) -> list[str]:
        return [item.content for item in self.deliverables]


class PlannedTaskDraft(BaseModel):
    """One task proposed by the planner (pre-validation)."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    completion_criteria: list[str] = Field(default_factory=list)
    deliverable: str | None = None
    deliverable_refs: list[str] = Field(default_factory=list)  # indices into spec.deliverables
    dependencies: list[str] = Field(default_factory=list)
    effort: Literal["small", "medium", "large"] = "medium"
    priority: Literal["low", "medium", "high"] = "medium"
    phase: str | None = None
    evidence_passages: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)


class WorkPackageDraft(BaseModel):
    """A major phase grouping related tasks."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    task_ids: list[str] = Field(default_factory=list)


class WorkBreakdown(BaseModel):
    """LLM-proposed hierarchical work breakdown (validated deterministically)."""

    project_type: ProjectType = "general"
    phases: list[WorkPackageDraft] = Field(default_factory=list)
    tasks: list[PlannedTaskDraft] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
