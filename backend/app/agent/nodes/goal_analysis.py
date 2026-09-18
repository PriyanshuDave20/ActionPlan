from app.agent.state import AgentState
from app.llm.provider import LLMProvider


def analyze_goal_node(state: AgentState, llm: LLMProvider) -> AgentState:
    work_request = state.get("work_request")

    if state.get("objective_analysis") is not None and state.get("planner_steps"):
        return {"execution_metadata": {"analysis": "reused"}}

    analysis = llm.analyze_objective(work_request)
    planner_steps = [
        "Analyze the goal and current situation.",
        "Extract applicable organizational procedures.",
        "Define the requirements the work must satisfy.",
        "Plan, validate, and optimize execution order.",
        "Detect blockers and recommend the next action.",
    ]

    return {
        "objective_analysis": analysis.model_dump(),
        "planner_steps": planner_steps,
        "execution_metadata": {"analysis": "completed"},
    }


def extract_procedures_node(state: AgentState, llm: LLMProvider) -> AgentState:
    if state.get("procedures"):
        return {"execution_metadata": {"procedures": "reused"}}

    work_request = state.get("work_request")
    extraction = llm.extract_procedures(work_request)
    return {
        "procedures": extraction.procedures,
        "procedure_analysis": {
            "summary": extraction.summary,
            "count": len(extraction.procedures),
            "notes": extraction.notes,
        },
        "execution_metadata": {"procedures": "completed"},
    }


def extract_requirements_node(state: AgentState, llm: LLMProvider) -> AgentState:
    if state.get("requirements"):
        return {"execution_metadata": {"requirements": "reused"}}

    work_request = state.get("work_request")
    extraction = llm.extract_requirements(work_request)
    return {
        "requirements": extraction.requirements,
        "execution_metadata": {"requirements": "completed"},
    }