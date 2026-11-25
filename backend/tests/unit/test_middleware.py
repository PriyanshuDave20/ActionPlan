import asyncio

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.api.middleware import SecurityHeadersMiddleware, TokenAuthMiddleware
from app.integrations.jira import JiraIntegration
from app.integrations.slack import SlackIntegration


def _secure_app() -> Starlette:
    async def secure(request):
        return JSONResponse({"ok": True})

    return Starlette(routes=[Route("/secure", secure)])


def test_optional_token_auth_blocks_unauthenticated_calls():
    client = TestClient(TokenAuthMiddleware(_secure_app(), tokens="secret-token"))
    assert client.get("/secure").status_code == 401
    assert client.get("/secure", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_optional_token_auth_accepts_valid_bearer_token():
    client = TestClient(TokenAuthMiddleware(_secure_app(), tokens="secret-token"))
    response = client.get("/secure", headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 200


def test_security_headers_are_added():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_slack_integration_posts_message():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hooks.slack.com"
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = asyncio.run(
        SlackIntegration("https://hooks.slack.com/services/test", client).post_message(text="hello")
    )
    assert result.ok is True
    assert result.provider == "slack"


def test_jira_integration_creates_issue():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"key": "ENG-1"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = asyncio.run(
        JiraIntegration(
            base_url="https://example.atlassian.net",
            email="ops@example.com",
            api_token="token",
            client=client,
        ).create_issue(
            project="ENG",
            summary="Next step",
            description="Approved recommendation",
            issue_type="Task",
        )
    )
    assert result.external_id == "ENG-1"
    assert result.url == "https://example.atlassian.net/browse/ENG-1"
