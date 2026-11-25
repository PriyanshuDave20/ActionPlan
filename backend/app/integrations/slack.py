import httpx

from app.integrations.models import IntegrationResult


class SlackIntegration:
    def __init__(self, webhook_url: str | None, client: httpx.AsyncClient | None = None) -> None:
        self.webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=15)

    async def post_message(self, *, text: str, channel: str | None = None) -> IntegrationResult:
        if not self.webhook_url:
            raise ValueError("Slack is not configured.")
        payload = {"text": text}
        if channel:
            payload["channel"] = channel
        response = await self._client.post(self.webhook_url, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"Slack returned HTTP {response.status_code}.")
        return IntegrationResult(
            provider="slack",
            external_id=response.headers.get("x-slack-message-id"),
            detail="Message delivered to Slack.",
        )
