from fastapi.testclient import TestClient

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service, get_retriever
from app.main import app


def _client(components) -> TestClient:
    llm, retriever, memory, _ = components
    app.dependency_overrides[get_agent_service] = lambda: AgentService(llm, retriever, memory)
    app.dependency_overrides[get_retriever] = lambda: retriever
    client = TestClient(app)
    return client


def test_create_goal_full_contract(components):
    client = _client(components)
    response = client.post(
        "/goals",
        json={
            "goal": "Prepare Project Alpha",
            "people_involved": [{"name": "Ada", "role": "lead"}],
            "priority": "high",
            "deadline": "2026-12-01",
            "success_criteria": ["Alpha is live"],
        },
    )
    assert response.status_code == 201
    body = response.json()
    # primary contract keys the frontend depends on
    for key in (
        "workflow_id",
        "work_request",
        "objective_analysis",
        "requirements",
        "candidate_plan",
        "plan_validation",
        "optimization",
        "recommendation",
        "tasks",
        "completed_tasks",
        "detected_blockers",
        "current_state",
    ):
        assert key in body, f"missing key {key}"

    task = body["tasks"][0]
    assert "id" in task
    assert task["status"] == "pending"
    assert task["effort"] in {"small", "medium", "large", "high"}
    assert body["work_request"]["goal"] == "Prepare Project Alpha"
    assert body["work_request"]["priority"] == "high"
    app.dependency_overrides.clear()


def test_continue_endpoint_completes_task(components):
    client = _client(components)
    created = client.post("/goals", json={"goal": "Ship the feature"}).json()
    workflow_id = created["workflow_id"]
    task_id = created["tasks"][0]["id"]
    response = client.post(f"/goals/{workflow_id}/continue", json={"completed_task_ids": [task_id]})
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"] == workflow_id
    assert task_id in body["completed_tasks"]
    app.dependency_overrides.clear()


def test_continue_endpoint_accepts_empty_body(components):
    client = _client(components)
    created = client.post("/goals", json={"goal": "Plan the retro"}).json()
    workflow_id = created["workflow_id"]
    response = client.post(f"/goals/{workflow_id}/continue", json={})
    assert response.status_code == 200
    app.dependency_overrides.clear()


def test_documents_ingest_endpoint(components):
    client = _client(components)
    response = client.post(
        "/documents/ingest",
        files={"file": ("policy.txt", b"Review every request before merging.", "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "policy.txt"
    assert body["chunks"] >= 1
    app.dependency_overrides.clear()


def test_workflows_list_and_detail(components):
    client = _client(components)
    created = client.post("/goals", json={"goal": "Organize the offsite"}).json()
    workflow_id = created["workflow_id"]
    summaries = client.get("/workflows").json()
    assert any(item["workflow_id"] == workflow_id for item in summaries)
    detail = client.get(f"/workflows/{workflow_id}")
    assert detail.status_code == 200
    assert detail.json()["original_goal"] == "Organize the offsite"
    app.dependency_overrides.clear()


def test_unknown_workflow_404(components):
    client = _client(components)
    response = client.get("/workflows/wf_missing")
    assert response.status_code == 404
    app.dependency_overrides.clear()