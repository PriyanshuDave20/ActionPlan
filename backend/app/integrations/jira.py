import httpx

from app.integrations.models import IntegrationResult


class JiraIntegration:
    def __init__(
        self,
        *,
        base_url: str | None,
        email: str | None,
        api_token: str | None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.email = email
        self.api_token = api_token
        self._client = client or httpx.AsyncClient(timeout=15)

    async def create_issue(
        self,
        *,
        project: str,
        summary: str,
        description: str,
        issue_type: str,
    ) -> IntegrationResult:
        if not self.base_url or not self.email or not self.api_token:
            raise ValueError("Jira is not configured.")
        response = await self._client.post(
            f"{self.base_url}/rest/api/3/issue",
            auth=(self.email, self.api_token),
            json={
                "fields": {
                    "project": {"key": project},
                    "summary": summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": description}],
                            }
                        ],
                    },
                    "issuetype": {"name": issue_type},
                }
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Jira returned HTTP {response.status_code}.")
        payload = response.json()
        key = payload.get("key")
        return IntegrationResult(
            provider="jira",
            external_id=key,
            url=f"{self.base_url}/browse/{key}" if key else None,
            detail="Issue created in Jira.",
        )
