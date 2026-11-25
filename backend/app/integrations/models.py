from pydantic import BaseModel, Field


class IntegrationResult(BaseModel):
    provider: str
    ok: bool = True
    external_id: str | None = None
    url: str | None = None
    detail: str = ""


class ExecutionRequest(BaseModel):
    version: int = Field(ge=1)
    message: str | None = Field(default=None, max_length=4000)
    channel: str | None = None
    jira_project: str | None = Field(default=None, min_length=1, max_length=64)
    jira_issue_type: str = Field(default="Task", min_length=1, max_length=64)
    notify_slack: bool = False
    create_jira_issue: bool = False
