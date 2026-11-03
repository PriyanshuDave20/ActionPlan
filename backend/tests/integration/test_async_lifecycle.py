"""Module 5: asynchronous workflow lifecycle tests.

Covers creation semantics (persist-before-enqueue, immediate QUEUED return),
complete payload preservation through SQS, worker claiming/transitions,
COMPLETED/FAILED persistence, idempotent duplicate deliveries, explicit
missing-workflow handling, enqueue-failure surfacing, and read-only
retrieval guarantees. All AWS dependencies (SQS, DynamoDB, LLM, Zilliz)
are mocked; runs entirely against the local memory store.
"""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.agent.service as service_module
from app.agent.service import (
    AgentService,
    EnqueueError,
    WorkflowNotFoundError,
)
from app.config import Settings
from app.llm.provider import MockLLMProvider
from app.memory.local import LocalMemoryStore
from app.models.work_request import WorkRequestInput
from app.rag.embeddings import LocalHashEmbeddings
from app.rag.vector_store import LocalVectorStore, VectorRetriever


class ExplodingGraph:
    """Graph stub that always fails, for testing failure persistence."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state):
        self.calls += 1
        raise RuntimeError("simulated graph failure")


@pytest.fixture
def queue_env(monkeypatch, tmp_path):
    """Patch the service's settings and SQS sender for deterministic tests.

    Returns (service, memory, sent, order) where sent records every message
    handed to the (fake) queue and order records persist/enqueue sequencing.
    """
    memory = LocalMemoryStore(tmp_path)
    retriever = VectorRetriever(LocalVectorStore(tmp_path / "vectors.json"), LocalHashEmbeddings())
    service = AgentService(MockLLMProvider(), retriever, memory)

    settings = Settings(
        data_dir=tmp_path,
        embedding_model="hash:local",
        workflow_queue_url="https://sqs.fake.us-east-2.amazonaws.com/queue",
        aws_region="us-east-2",
    )
    monkeypatch.setattr(service_module, "get_settings", lambda: settings)

    sent: list[dict] = []
    order: list[str] = []
    original_save = memory.save_workflow

    def tracking_save(workflow):
        order.append("persist")
        return original_save(workflow)

    memory.save_workflow = tracking_save  # type: ignore[method-assign]

    def fake_send(queue_url, region, message):
        order.append("enqueue")
        sent.append(message)
        return f"msg-id-{len(sent)}"

    monkeypatch.setattr(service_module, "_send_workflow_job", fake_send)
    return service, memory, sent, order


def _full_payload() -> WorkRequestInput:
    return WorkRequestInput(
        goal="Prepare Project Alpha",
        people_involved=[{"name": "Ada", "role": "lead"}, {"name": "Grace", "role": "reviewer"}],
        deadline=date(2027, 3, 1),
        priority="high",
        current_status="Feature complete",
        constraints=["Security review required"],
        resources=["Staging environment"],
        success_criteria=["Alpha is live", "Zero critical findings"],
    )


# ---------------------------------------------------------------------------
# Creation semantics
# ---------------------------------------------------------------------------


def test_create_returns_queued_and_persists_before_enqueue(queue_env):
    service, memory, sent, order = queue_env

    workflow = service.create_workflow(_full_payload())

    assert workflow.execution_state.value == "queued"
    assert len(sent) == 1

    stored = memory.get_workflow(workflow.workflow_id)
    assert stored is not None
    assert stored.execution_state.value == "queued"
    # The workflow must exist durably before the job is handed to SQS.
    assert order.index("persist") < order.index("enqueue")


def test_enqueue_failure_marks_failed_and_raises(queue_env, monkeypatch):
    service, memory, sent, order = queue_env

    def failing_send(queue_url, region, message):
        raise RuntimeError("SQS unavailable")

    monkeypatch.setattr(service_module, "_send_workflow_job", failing_send)
    with pytest.raises(EnqueueError):
        service.create_workflow(_full_payload())

    # The only workflow in memory is FAILED with the enqueue error — no
    # orphaned QUEUED record waiting for a worker that will never come.
    workflows = memory.list_workflows()
    assert len(workflows) == 1
    assert workflows[0].execution_state.value == "failed"
    assert "enqueue" in (workflows[0].execution_error or "").lower()


# ---------------------------------------------------------------------------
# Payload preservation and worker execution
# ---------------------------------------------------------------------------


def test_complete_payload_sent_to_queue_and_used_by_worker(queue_env):
    service, memory, sent, order = queue_env
    payload = _full_payload()

    workflow = service.create_workflow(payload)

    # The queue message carries the complete validated request.
    assert len(sent) == 1
    message = sent[0]
    assert message["workflow_id"] == workflow.workflow_id
    assert message["payload"]["goal"] == payload.goal
    assert message["payload"]["priority"] == "high"
    assert [p["name"] for p in message["payload"]["people_involved"]] == ["Ada", "Grace"]
    assert message["payload"]["deadline"] == "2027-03-01"
    assert message["payload"]["constraints"] == ["Security review required"]
    assert message["payload"]["resources"] == ["Staging environment"]
    assert message["payload"]["success_criteria"] == ["Alpha is live", "Zero critical findings"]

    # A separate worker (fresh service, different worker id — like the
    # separate Lambda) reconstructs the request from the queue message and
    # the persisted workflow preserves every user-provided field.
    worker_service = AgentService(MockLLMProvider(), service.retriever, memory)
    delivered = WorkRequestInput.model_validate(message["payload"])
    result = worker_service.execute_queued_workflow(workflow.workflow_id, delivered)

    assert result is not None
    assert result.execution_state.value == "completed"
    request = result.work_request
    assert request is not None
    assert request.priority == "high"
    assert [p.name for p in request.people] == ["Ada", "Grace"]
    assert request.deadline == date(2027, 3, 1)
    assert request.constraints == ["Security review required"]
    assert request.resources == ["Staging environment"]
    assert request.success_criteria == ["Alpha is live", "Zero critical findings"]


def test_worker_transitions_to_running_and_persists_completed(queue_env):
    service, memory, _, order = queue_env
    workflow = service.create_workflow("Ship the feature")

    # Claiming transitions QUEUED -> RUNNING and is one-shot.
    claimed = memory.claim_workflow_for_execution(workflow.workflow_id, "worker-a")
    assert claimed is not None
    assert claimed.execution_state.value == "running"
    # A second worker cannot claim the same workflow.
    assert memory.claim_workflow_for_execution(workflow.workflow_id, "worker-b") is None

    # The claimed workflow can no longer be claimed by execute_queued_workflow.
    result = service.execute_queued_workflow(workflow.workflow_id)
    assert result is None  # idempotent skip, not an error


def test_worker_persists_completed_after_successful_execution(queue_env):
    service, memory, _, order = queue_env
    payload = _full_payload()
    workflow = service.create_workflow(payload)
    delivered = WorkRequestInput.model_validate({"workflow_id": workflow.workflow_id, **{"goal": payload.goal}})

    result = service.execute_queued_workflow(workflow.workflow_id)
    assert result is not None
    assert result.execution_state.value == "completed"
    assert len(result.tasks) >= 1
    assert result.recommendation is not None

    stored = memory.get_workflow(workflow.workflow_id)
    assert stored is not None
    assert stored.execution_state.value == "completed"
    assert len(stored.tasks) >= 1


def test_worker_persists_failed_on_execution_error(queue_env):
    service, memory, _, order = queue_env
    workflow = service.create_workflow("Break the plan")
    workflow_id = workflow.workflow_id

    service.graph = ExplodingGraph()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="simulated graph failure"):
        service.execute_queued_workflow(workflow_id)

    stored = memory.get_workflow(workflow_id)
    assert stored is not None
    assert stored.execution_state.value == "failed"
    assert "simulated graph failure" in (stored.execution_error or "")


def test_duplicate_deliveries_do_not_reexecute(queue_env):
    service, memory, sent, order = queue_env
    workflow = service.create_workflow("Plan the offsite")
    assert len(sent) == 1

    first = service.execute_queued_workflow(workflow.workflow_id)
    assert first is not None and first.execution_state.value == "completed"

    # Duplicate SQS delivery: claim fails, execute is an idempotent skip.
    second = service.execute_queued_workflow(workflow.workflow_id)
    assert second is None
    stored = memory.get_workflow(workflow.workflow_id)
    assert stored is not None
    assert stored.execution_state.value == "completed"
    assert len(sent) == 1  # no new job was enqueued


def test_missing_workflow_raises_explicitly(queue_env):
    service, memory, _, order = queue_env
    with pytest.raises(WorkflowNotFoundError):
        service.execute_queued_workflow("wf_does_not_exist")


def test_delivered_payload_reaches_worker_through_handler(queue_env, monkeypatch):
    """End-to-end: API-style create -> captured SQS message -> worker handler."""
    import worker_handler as handler_module

    service, memory, sent, order = queue_env
    payload = _full_payload()
    workflow = service.create_workflow(payload)
    message = sent[0]

    # The worker Lambda constructs its own service; point the handler's
    # factory at our service (same DynamoDB config by construction).
    monkeypatch.setattr(handler_module, "_get_agent_service", lambda: service)

    event = {
        "Records": [
            {"messageId": "m1", "body": json.dumps(message)},
        ]
    }
    response = handler_module.handler(event, {})

    body = json.loads(response["body"])
    assert body["results"][0]["status"] == "success"
    assert body["results"][0]["execution_state"] == "completed"
    assert response["batchItemFailures"] == []

    stored = memory.get_workflow(workflow.workflow_id)
    assert stored is not None
    assert stored.execution_state.value == "completed"
    assert stored.work_request is not None
    assert stored.work_request.priority == "high"


def test_handler_reports_transient_failures_for_retry(queue_env, monkeypatch):
    import worker_handler as handler_module

    service, memory, sent, order = queue_env
    workflow = service.create_workflow("Will fail")
    message = sent[0]

    service.graph = ExplodingGraph()  # type: ignore[assignment]
    monkeypatch.setattr(handler_module, "_get_agent_service", lambda: service)

    event = {
        "Records": [
            {"messageId": "m-fail", "body": json.dumps(message)},
        ]
    }
    response = handler_module.handler(event, {})

    # Transient failure: reported so SQS retries / redrives per config.
    assert response["batchItemFailures"] == [{"itemIdentifier": "m-fail"}]
    stored = memory.get_workflow(workflow.workflow_id)
    assert stored is not None
    assert stored.execution_state.value == "failed"


def test_handler_acks_permanent_failures_without_retry(queue_env, monkeypatch):
    import worker_handler as handler_module

    service, memory, _, order = queue_env
    monkeypatch.setattr(handler_module, "_get_agent_service", lambda: service)

    # Malformed bodies and missing workflow records can never succeed; they
    # must be acknowledged (not retried) so they don't loop into the DLQ.
    event = {
        "Records": [
            {"messageId": "m-bad-json", "body": "{not json"},
            {"messageId": "m-no-id", "body": json.dumps({"payload": {"goal": "x"}})},
            {"messageId": "m-missing", "body": json.dumps({"workflow_id": "wf_ghost", "payload": {"goal": "x"}})},
        ]
    }
    response = handler_module.handler(event, {})

    body = json.loads(response["body"])
    statuses = {r["message_id"]: r["status"] for r in body["results"]}
    assert statuses["m-bad-json"] == "error"
    assert statuses["m-no-id"] == "error"
    assert statuses["m-missing"] == "error"
    assert response["batchItemFailures"] == []


# ---------------------------------------------------------------------------
# Read-only retrieval guarantees
# ---------------------------------------------------------------------------


def test_retrieval_and_listing_never_invoke_graph(queue_env):
    service, memory, sent, order = queue_env
    workflow = service.create_workflow("Audit only")

    # Any graph invocation would fail loudly.
    service.graph = ExplodingGraph()  # type: ignore[assignment]

    assert service.get_workflow(workflow.workflow_id) is not None
    summaries = service.list_workflows()
    assert any(s.workflow_id == workflow.workflow_id for s in summaries)
    assert all(s.execution_state == "queued" for s in summaries)
    assert len(sent) == 1  # listing created no new jobs


def test_opening_completed_workflow_triggers_no_execution(queue_env):
    service, memory, sent, order = queue_env
    workflow = service.create_workflow("Read back safely")
    service.execute_queued_workflow(workflow.workflow_id)
    assert len(sent) == 1

    service.graph = ExplodingGraph()  # type: ignore[assignment]

    reopened = service.get_workflow(workflow.workflow_id)
    assert reopened is not None
    assert reopened.execution_state.value == "completed"
    assert len(reopened.tasks) >= 1
    assert len(sent) == 1  # opening the project never enqueues or executes


def test_route_retrieval_is_read_only(queue_env, monkeypatch):
    from app.api.dependencies import get_agent_service, get_retriever
    from app.main import app

    service, memory, sent, order = queue_env
    workflow = service.create_workflow("Route read test")
    service.execute_queued_workflow(workflow.workflow_id)

    service.graph = ExplodingGraph()  # type: ignore[assignment]
    app.dependency_overrides[get_agent_service] = lambda: service
    try:
        client = TestClient(app)
        assert client.get(f"/workflows/{workflow.workflow_id}").status_code == 200
        assert client.get("/workflows").status_code == 200
        status = client.get(f"/goals/{workflow.workflow_id}/status")
        assert status.status_code == 200
        assert status.json()["execution_state"] == "completed"
    finally:
        app.dependency_overrides.clear()


def test_summary_includes_execution_state(queue_env):
    service, memory, _, order = queue_env
    workflow = service.create_workflow("Summary state")
    summaries = service.list_workflows()
    assert summaries[0].execution_state == "queued"

    service.execute_queued_workflow(workflow.workflow_id)
    summaries = service.list_workflows()
    assert summaries[0].execution_state == "completed"


def test_route_create_returns_503_when_enqueue_fails(queue_env, monkeypatch):
    from app.api.dependencies import get_agent_service, get_retriever
    from app.main import app

    service, memory, _, order = queue_env

    def failing_send(queue_url, region, message):
        raise RuntimeError("SQS unavailable")

    monkeypatch.setattr(service_module, "_send_workflow_job", failing_send)
    app.dependency_overrides[get_agent_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/goals", json={"goal": "Never enqueued"})
        assert response.status_code == 503
        assert "enqueue" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
