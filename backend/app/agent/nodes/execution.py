from app.agent.state import AgentState


def execute_plan_node(state: AgentState) -> AgentState:
    tasks = state.get("tasks", [])
    completed = set(state.get("completed_tasks", []))

    for task in tasks:
        if task.id in completed:
            task.status = "completed"

    current_task = None
    for task in tasks:
        if task.status != "completed":
            current_task = task.id
            break

    return {
        "tasks": tasks,
        "current_task": current_task,
        "execution_metadata": {"execution": "completed"},
    }