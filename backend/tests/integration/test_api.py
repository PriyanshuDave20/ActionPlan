from fastapi.testclient import TestClient

from app.api.dependencies import get_agent_service, get_retriever
from app.main import app


def test_health_and_goal_api(components):
    llm, retriever, memory, _ = components
    from app.agent.service import AgentService

    app.dependency_overrides[get_agent_service] = lambda: AgentService(llm, retriever, memory)
    app.dependency_overrides[get_retriever] = lambda: retriever
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/goals", json={"goal": "Prepare a launch"})
    assert response.status_code == 201
    workflow_id = response.json()["workflow_id"]
    assert client.get(f"/workflows/{workflow_id}").status_code == 200
    app.dependency_overrides.clear()
