"""Lambda / Mangum adapter tests.

These tests exercise the Lambda handler module and representative API Gateway
HTTP API events through Mangum -> FastAPI. They use the same mocked components
as the rest of the suite and never call NVIDIA, Zilliz, or DynamoDB.
"""

import json
import os
import tempfile

from app.config import get_settings


def _api_gateway_event(
    method: str,
    path: str,
    body: str | None = None,
    headers: dict | None = None,
) -> dict:
    request_headers = {"content-type": "application/json"}
    if headers:
        request_headers.update(headers)
    event = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": request_headers,
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "testapi",
            "domainName": "testapi.execute-api.us-east-2.amazonaws.com",
            "domainPrefix": "testapi",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.1",
                "userAgent": "curl",
            },
            "requestId": "test-request",
            "routeKey": f"{method} {path}",
            "stage": "$default",
            "time": "15/Sep/2026:00:00:00 +0000",
            "timeEpoch": 0,
        },
        "isBase64Encoded": False,
    }
    if body is not None:
        event["body"] = body
    return event


def _fresh_app_with_frontend_origin(origin: str):
    """Build a fresh FastAPI app whose CORS allow-list includes `origin`.

    app.main reads get_settings() at import time, so this reloads the module
    after pointing FRONTEND_ORIGIN at the requested value. The previously
    imported app remains untouched (other tests keep their own handle).
    """
    import importlib

    get_settings.cache_clear()
    os.environ["FRONTEND_ORIGIN"] = origin
    main = importlib.import_module("app.main")
    importlib.reload(main)
    return main.app


def test_lambda_handler_import_and_health_event(components):
    import lambda_handler

    assert callable(lambda_handler.handler)
    assert lambda_handler.app.title == "AI Workplace Operations Agent"

    llm, retriever, memory, _ = components
    from app.agent.service import AgentService
    from app.api.dependencies import get_agent_service, get_retriever

    app = lambda_handler.app
    app.dependency_overrides[get_agent_service] = lambda: AgentService(llm, retriever, memory)
    app.dependency_overrides[get_retriever] = lambda: retriever
    try:
        event = _api_gateway_event("GET", "/health")
        response = lambda_handler.handler(event, {})
        assert response["statusCode"] == 200
        assert json.loads(response["body"]) == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()


def test_post_goals_event_translation(components):
    import lambda_handler

    llm, retriever, memory, _ = components
    from app.agent.service import AgentService
    from app.api.dependencies import get_agent_service, get_retriever

    app = lambda_handler.app
    app.dependency_overrides[get_agent_service] = lambda: AgentService(llm, retriever, memory)
    app.dependency_overrides[get_retriever] = lambda: retriever
    try:
        event = _api_gateway_event(
            "POST",
            "/goals",
            body=json.dumps({"goal": "Prepare a launch"}),
        )
        response = lambda_handler.handler(event, {})
        assert response["statusCode"] == 201
        payload = json.loads(response["body"])
        assert payload["workflow_id"]
        assert payload["original_goal"] == "Prepare a launch"
        assert payload["tasks"]
    finally:
        app.dependency_overrides.clear()


def test_unknown_workflow_event_404(components):
    import lambda_handler

    llm, retriever, memory, _ = components
    from app.agent.service import AgentService
    from app.api.dependencies import get_agent_service, get_retriever

    app = lambda_handler.app
    app.dependency_overrides[get_agent_service] = lambda: AgentService(llm, retriever, memory)
    app.dependency_overrides[get_retriever] = lambda: retriever
    try:
        event = _api_gateway_event("GET", "/workflows/wf_missing")
        response = lambda_handler.handler(event, {})
        assert response["statusCode"] == 404
    finally:
        app.dependency_overrides.clear()


def test_cors_origin_configurable_via_frontend_origin():
    origin = "https://product.amplifyapp.com"
    get_settings.cache_clear()
    os.environ["FRONTEND_ORIGIN"] = origin
    try:
        settings = get_settings()
        assert origin in settings.resolved_cors_origins
        assert "http://localhost:5173" in settings.resolved_cors_origins
    finally:
        os.environ.pop("FRONTEND_ORIGIN", None)
        get_settings.cache_clear()


def test_cors_header_present_for_allowed_origin():
    origin = "https://product.amplifyapp.com"
    app = _fresh_app_with_frontend_origin(origin)
    try:
        from mangum import Mangum

        handler = Mangum(app, lifespan="off")
        event = _api_gateway_event(
            "GET",
            "/health",
            headers={"origin": origin, "access-control-request-method": "GET"},
        )
        response = handler(event, {})
        assert response["statusCode"] == 200
        headers = {key.lower(): value for key, value in response.get("headers", {}).items()}
        assert headers.get("access-control-allow-origin") == origin
    finally:
        os.environ.pop("FRONTEND_ORIGIN", None)
        get_settings.cache_clear()


def test_data_dir_can_target_tmp_for_lambda():
    """Lambda has no persistent data dir; MEMORY_BACKEND=local must be able
    to write under /tmp for dev parity without touching repository state."""
    from app.memory.local import LocalMemoryStore
    from app.models.workflow import WorkflowState

    tmp = tempfile.mkdtemp(prefix="wf-lambda-")
    memory = LocalMemoryStore(tmp)
    workflow = WorkflowState(workflow_id="tmp-one", original_goal="tmp test")
    memory.save_workflow(workflow)
    assert memory.get_workflow("tmp-one").original_goal == "tmp test"