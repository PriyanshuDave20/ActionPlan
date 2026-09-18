from app.agent.state import AgentState


def state_analysis_node(state: AgentState) -> AgentState:
    tasks = state.get("tasks", [])
    completed = set(state.get("completed_tasks", []))

    pending = [task.id for task in tasks if task.id not in completed]
    progress = round(
        (len(completed) / len(tasks)) * 100 if tasks else 0.0
    )

    if not tasks:
        status = "No plan produced."
    elif pending:
        status = f"Execution in progress: task {len(completed) + 1} of {len(tasks)}."
    else:
        status = "All planned tasks are complete."

    return {
        "current_state": {
            "status": status,
            "progress": progress,
            "completed_task_ids": sorted(completed),
            "pending_task_ids": pending,
        },
        "execution_metadata": {"state_analysis": "completed"},
    }