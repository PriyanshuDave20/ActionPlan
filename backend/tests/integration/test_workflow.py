from app.agent.service import AgentService


def test_langgraph_workflow_executes_and_persists(components):
    llm, retriever, memory, _ = components
    service = AgentService(llm, retriever, memory)
    workflow = service.create_workflow("Prepare Project Alpha for production")
    assert workflow.workflow_id
    assert len(workflow.tasks) == 4
    assert workflow.recommendation is not None
    assert memory.get_workflow(workflow.workflow_id) is not None
    continued = service.continue_workflow(workflow.workflow_id)
    assert continued.workflow_id == workflow.workflow_id
