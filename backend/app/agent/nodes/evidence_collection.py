from app.agent.state import AgentState
from app.models.evidence import Evidence
from app.models.optimization import TargetedEvidence
from app.rag.vector_store import VectorRetriever


def collect_evidence_node(state: AgentState, retriever: VectorRetriever) -> AgentState:
    if state.get("targeted_evidence"):
        return {"execution_metadata": {"evidence": "reused"}}

    requirements = state.get("requirements", [])
    targeted: list[TargetedEvidence] = []
    by_requirement: dict[str, list[str]] = {}
    all_evidence: list[Evidence] = []

    for requirement in requirements:
        hits = retriever.retrieve(requirement.text, limit=3) or []
        targeted.append(
            TargetedEvidence(
                requirement_id=requirement.id,
                query=requirement.text,
                evidence=hits,
            )
        )
        by_requirement[requirement.id] = [
            evidence.source or evidence.content[:48] for evidence in hits
        ]
        all_evidence.extend(hits)

    return {
        "targeted_evidence": targeted,
        "targeted_by_requirement": by_requirement,
        "retrieved_documents": all_evidence,
        "execution_metadata": {"evidence": "completed"},
    }