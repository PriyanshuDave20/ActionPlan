from app.agent.service import AgentService


def test_create_workflow_with_input_object(components):
    llm, retriever, memory, _ = components
    from app.models.work_request import WorkRequestInput

    service = AgentService(llm, retriever, memory)
    workflow = service.create_workflow(
        WorkRequestInput(goal="Prepare the annual audit", deadline=None)
    )
    assert workflow.workflow_id
    assert len(workflow.tasks) == 4


def test_create_workflow_with_string(components):
    llm, retriever, memory, _ = components
    service = AgentService(llm, retriever, memory)
    workflow = service.create_workflow("Deploy the staging environment")
    assert workflow.workflow_id
    assert workflow.original_goal == "Deploy the staging environment"


def test_continue_marks_task_completed(components):
    llm, retriever, memory, _ = components
    service = AgentService(llm, retriever, memory)
    workflow = service.create_workflow("Migrate the database")
    first = workflow.tasks[0]
    from app.models.workflow import WorkflowState

    workflow_stored: WorkflowState = memory.get_workflow(workflow.workflow_id)
    continued = service.continue_workflow(workflow_stored, [first.id])
    assert first.id in continued.completed_tasks
    assert continued.workflow_id == workflow.workflow_id


def test_continue_returns_none_for_unknown_id(components):
    llm, retriever, memory, _ = components
    service = AgentService(llm, retriever, memory)
    assert service.continue_workflow("wf_does_not_exist") is None


def test_list_summaries(components):
    llm, retriever, memory, _ = components
    service = AgentService(llm, retriever, memory)
    service.create_workflow("Recruit an intern")
    summaries = service.list_workflows()
    assert summaries
    assert summaries[0].goal == "Recruit an intern"
    assert summaries[0].total_tasks == 4


def test_workflow_persists_to_memory(components):
    llm, retriever, memory, _ = components
    service = AgentService(llm, retriever, memory)
    workflow = service.create_workflow("Update the policy handbook")
    stored = memory.get_workflow(workflow.workflow_id)
    assert stored is not None
    assert stored.original_goal == "Update the policy handbook"