from langgraph.graph import END, StateGraph

from app.agent.nodes.blocker_detection import detect_blocker_node
from app.agent.nodes.evidence_collection import collect_evidence_node
from app.agent.nodes.execution import execute_plan_node
from app.agent.nodes.goal_analysis import (
    analyze_goal_node,
    extract_procedures_node,
    extract_requirements_node,
)
from app.agent.nodes.initialization import initialize_node
from app.agent.nodes.memory import update_memory_node
from app.agent.nodes.plan_validation import should_revise, validate_plan_node, revise_plan_node
from app.agent.nodes.planning import create_plan_node
from app.agent.nodes.recommendation import recommendation_node
from app.agent.nodes.state_analysis import state_analysis_node
from app.agent.state import AgentState


def build_graph(
    llm,
    retriever,
    memory,
):
    """Compile the linear advisory workflow into a runnable LangGraph."""

    def bind(node, **deps):
        def wrapper(state: AgentState) -> AgentState:
            return node(state, **deps)

        return wrapper

    graph = StateGraph(AgentState)

    graph.add_node("initialize_node", initialize_node)
    graph.add_node("analyze_goal", bind(analyze_goal_node, llm=llm))
    graph.add_node("extract_procedures", bind(extract_procedures_node, llm=llm))
    graph.add_node("extract_requirements", bind(extract_requirements_node, llm=llm))
    graph.add_node("collect_evidence", bind(collect_evidence_node, retriever=retriever))
    graph.add_node("plan", create_plan_node)
    graph.add_node("validate_plan", validate_plan_node)
    graph.add_node("revise_plan", revise_plan_node)
    graph.add_node("execute_plan", execute_plan_node)
    graph.add_node("optimize_plan", optimize_plan_node)
    graph.add_node("state_analysis", state_analysis_node)
    graph.add_node("detect_blockers", detect_blocker_node)
    graph.add_node("recommend", recommendation_node)
    graph.add_node("update_memory", bind(update_memory_node, memory=memory))

    graph.add_edge("initialize_node", "analyze_goal")
    graph.add_edge("analyze_goal", "extract_procedures")
    graph.add_edge("extract_procedures", "extract_requirements")
    graph.add_edge("extract_requirements", "collect_evidence")
    graph.add_edge("collect_evidence", "plan")
    graph.add_edge("plan", "validate_plan")
    graph.add_conditional_edges(
        "validate_plan",
        should_revise,
        {"revise_plan": "revise_plan", "execute_plan": "execute_plan"},
    )
    graph.add_edge("revise_plan", "plan")
    graph.add_edge("execute_plan", "optimize_plan")
    graph.add_edge("optimize_plan", "state_analysis")
    graph.add_edge("state_analysis", "detect_blockers")
    graph.add_edge("detect_blockers", "recommend")
    graph.add_edge("recommend", "update_memory")
    graph.add_edge("update_memory", END)

    graph.set_entry_point("initialize_node")
    return graph.compile()


def optimize_plan_node(state: AgentState) -> AgentState:
    from app.agent.optimization import optimize_plan
    from app.models.work_request import WorkRequest

    candidate = state.get("candidate_plan")
    work_request: WorkRequest | None = state.get("work_request")
    if candidate is None or work_request is None:
        return {"execution_metadata": {"optimization": "skipped"}}

    result = optimize_plan(
        candidate_plan=candidate,
        deadline=work_request.deadline,
        completed_task_ids=state.get("completed_tasks", []),
    )
    return {
        "optimization": result,
        "execution_metadata": {"optimization": "completed"},
    }