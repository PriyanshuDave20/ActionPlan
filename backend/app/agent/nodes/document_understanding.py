"""Document-understanding stage: extract a structured project specification
from every available project document before any task is generated.

Retrieval is deliberately multi-probe: a single top-k query does not give
sufficient coverage of a document, so the node issues one query per
information need (objective, methodology, deliverables, deadlines, people,
constraints, risks...) and merges the results. Each extracted fact keeps
its document/page provenance; anything the documents do not state lands in
``missing_information`` rather than being invented.
"""

import json
import logging

from app.agent.state import AgentState
from app.models.project_spec import ProjectSpecification
from app.llm.provider import LLMProvider
from app.rag.vector_store import VectorRetriever

logger = logging.getLogger(__name__)

# One retrieval probe per information need. Queries are deterministic so
# the stage is observable and cheap (no LLM calls for query generation).
_RETRIEVAL_PROBES: tuple[tuple[str, str], ...] = (
    ("objective", "project objective aim purpose"),
    ("methodology", "methodology approach methods pipeline"),
    ("activities", "major activities steps tasks work"),
    ("deliverables", "deliverables final report outputs"),
    ("milestones", "milestones timeline schedule weeks"),
    ("deadlines", "deadline due dates submission"),
    ("constraints", "constraints limitations requirements must"),
    ("resources", "resources datasets tools available"),
    ("people", "team members responsibilities roles"),
    ("evaluation", "evaluation criteria grading success"),
    ("risks", "risks fallback limitations concerns"),
)

_PROBES_PER_NEED = 2
_CHUNK_CHARS = 700


def _context_line(document: str, page: int | None, text: str) -> str:
    return json.dumps(
        {"document": document, "page": page, "text": text[:_CHUNK_CHARS]},
        ensure_ascii=False,
    )


def understand_documents_node(state: AgentState, llm: LLMProvider, retriever: VectorRetriever) -> AgentState:
    if state.get("project_specification"):
        return {"execution_metadata": {"understanding": "reused"}}

    goal = state.get("original_goal", "")
    workflow_id = state.get("workflow_id")

    # Multi-probe retrieval for broad document coverage.
    lines: list[str] = []
    seen_texts: set[str] = set()
    for _need, probe in _RETRIEVAL_PROBES:
        try:
            if workflow_id:
                hits = retriever.retrieve(probe, limit=_PROBES_PER_NEED, workflow_id=workflow_id) or []
            else:
                hits = retriever.retrieve(probe, limit=_PROBES_PER_NEED) or []
        except Exception:
            logger.exception("Retrieval probe failed during document understanding")
            hits = []
        for evidence in hits:
            key = evidence.content[:120]
            if key in seen_texts:
                continue
            seen_texts.add(key)
            lines.append(_context_line(evidence.source or "", evidence.page, evidence.content))

    context = "\n".join(lines) if lines else "(no project documents were indexed for this goal)"

    try:
        spec = llm.understand_documents(goal, context)
    except Exception:
        logger.exception("Document understanding failed; continuing with an empty specification")
        spec = ProjectSpecification(
            title=goal,
            project_type="general",
            missing_information=[
                "Document understanding failed; the plan will rely on the goal text only.",
            ],
        )

    if not spec.search_queries:
        spec.search_queries = [goal]

    return {
        "project_specification": spec.model_dump(),
        "execution_metadata": {"understanding": "completed" if lines else "no_documents"},
    }
