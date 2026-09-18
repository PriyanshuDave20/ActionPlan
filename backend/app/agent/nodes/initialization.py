from app.agent.state import AgentState
from app.models.work_request import WorkRequestInput, compile_work_request


def initialize_node(state: AgentState) -> AgentState:
    incoming = list(state.get("incoming_completed_task_ids") or [])

    if state.get("work_request") is None:
        payload = state.get("work_request_input") or WorkRequestInput(
            goal=state.get("original_goal", "")
        )
        state["work_request"] = compile_work_request(payload)

    tasks = list(state.get("tasks", []))
    completed = set(state.get("completed_tasks", []))
    changed = False

    for task in tasks:
        if task.id in incoming and task.status != "completed":
            task.status = "completed"
            completed.add(task.id)
            changed = True

    if changed:
        state["tasks"] = tasks

    merged_completed = sorted(set(state.get("completed_tasks", [])) | completed)
    state["completed_tasks"] = merged_completed

    state["execution_metadata"] = {
        **state.get("execution_metadata", {}),
        "initialization": "completed",
    }
    return state