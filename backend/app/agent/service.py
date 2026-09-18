from uuid import uuid4

from app.agent.graph import build_graph
from app.agent.state import AgentState
from app.memory.interface import MemoryInterface
from app.models.work_request import WorkRequestInput
from app.models.workflow import WorkflowState, WorkflowSummary


def _generate_workflow_id(goal: str) -> str:
    slug = "".join(character for character in goal.lower() if character.isalnum() or character.isspace())
    slug = "-".join(slug.split())[:40]
    return f"wf_{slug or 'goal'}_{uuid4().hex[:8]}"


class AgentService:
    def __init__(self, llm, retriever, memory: MemoryInterface) -> None:
        self.llm = llm
        self.retriever = retriever
        self.memory = memory
        self.graph = build_graph(llm, retriever, memory)

    def create_workflow(self, goal_or_input: str | WorkRequestInput) -> WorkflowState:
        if isinstance(goal_or_input, str):
            payload = WorkRequestInput(goal=goal_or_input)
        else:
            payload = goal_or_input

        workflow_id = _generate_workflow_id(payload.goal)
        initial_state: AgentState = {
            "workflow_id": workflow_id,
            "original_goal": payload.goal,
            "work_request_input": payload,
            "incoming_completed_task_ids": [],
            "completed_tasks": [],
            "plan_revision_count": 0,
            "execution_metadata": {"created": True},
        }
        result = self.graph.invoke(initial_state)
        return self._to_workflow_state(result)

    def continue_workflow(
        self,
        workflow_id: str | WorkflowState,
        completed_task_ids: list[str] | None = None,
    ) -> WorkflowState | None:
        if isinstance(workflow_id, str):
            workflow = self.memory.get_workflow(workflow_id)
            if workflow is None:
                return None
        else:
            workflow = workflow_id
        state = self._to_agent_state(workflow)
        state["incoming_completed_task_ids"] = list(completed_task_ids or [])
        result = self.graph.invoke(state)
        return self._to_workflow_state(result)

    def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        return self.memory.get_workflow(workflow_id)

    def list_workflows(self) -> list[WorkflowSummary]:
        return [
            _to_summary(workflow)
            for workflow in self.memory.list_workflows()
        ]

    @staticmethod
    def _to_agent_state(workflow: WorkflowState) -> AgentState:
        state: AgentState = {
            "workflow_id": workflow.workflow_id,
            "original_goal": workflow.original_goal,
            "work_request": workflow.work_request,
            "work_request_input": None,
            "objective_analysis": workflow.objective_analysis,
            "goal_analysis": workflow.goal_analysis,
            "planner_steps": workflow.planner_steps,
            "procedure_analysis": workflow.procedure_analysis,
            "procedures": workflow.procedures,
            "requirements": workflow.requirements,
            "candidate_plan": workflow.candidate_plan,
            "plan_validation": workflow.plan_validation,
            "plan_revision_count": workflow.plan_revision_count,
            "optimization": workflow.optimization,
            "tasks": workflow.tasks,
            "completed_tasks": workflow.completed_tasks,
            "blocked_tasks": workflow.blocked_tasks,
            "current_task": workflow.current_task,
            "current_state": workflow.current_state,
            "function_definitions": workflow.function_definitions,
            "retrieved_documents": workflow.retrieved_documents,
            "targeted_evidence": workflow.targeted_evidence,
            "targeted_by_requirement": workflow.targeted_by_requirement,
            "detected_blockers": workflow.detected_blockers,
            "recommendation": workflow.recommendation,
            "memory_context": workflow.memory_context,
            "execution_metadata": workflow.execution_metadata,
        }
        return state

    @staticmethod
    def _to_workflow_state(state: AgentState) -> WorkflowState:
        mapping = {
            "work_request": "work_request",
            "objective_analysis": "objective_analysis",
            "goal_analysis": "goal_analysis",
            "planner_steps": "planner_steps",
            "procedure_analysis": "procedure_analysis",
            "procedures": "procedures",
            "requirements": "requirements",
            "candidate_plan": "candidate_plan",
            "plan_validation": "plan_validation",
            "plan_revision_count": "plan_revision_count",
            "optimization": "optimization",
            "tasks": "tasks",
            "completed_tasks": "completed_tasks",
            "blocked_tasks": "blocked_tasks",
            "current_task": "current_task",
            "current_state": "current_state",
            "function_definitions": "function_definitions",
            "retrieved_documents": "retrieved_documents",
            "targeted_evidence": "targeted_evidence",
            "targeted_by_requirement": "targeted_by_requirement",
            "detected_blockers": "detected_blockers",
            "recommendation": "recommendation",
            "memory_context": "memory_context",
            "execution_metadata": "execution_metadata",
        }
        workflow = WorkflowState(
            workflow_id=state.get("workflow_id", ""),
            original_goal=state.get("original_goal", ""),
        )
        for state_key, workflow_key in mapping.items():
            value = state.get(state_key)
            if value is not None:
                setattr(workflow, workflow_key, value)
        return workflow


def _to_summary(workflow: WorkflowState) -> WorkflowSummary:
    work_request = workflow.work_request
    return WorkflowSummary(
        workflow_id=workflow.workflow_id,
        goal=workflow.original_goal,
        updated_at=workflow.updated_at,
        deadline=work_request.deadline if work_request else None,
        priority=(work_request.priority or "medium") if work_request else "medium",
        total_tasks=len(workflow.tasks),
        completed_tasks=len([
            task for task in workflow.tasks if task.status == "completed"
        ]),
        blocker_count=len(workflow.detected_blockers),
        recommendation_action=(
            workflow.recommendation.action if workflow.recommendation else None
        ),
    )