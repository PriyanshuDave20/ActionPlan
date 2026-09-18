import json

import boto3
from botocore.exceptions import ClientError

from app.config import Settings
from app.models.workflow import WorkflowState

_PRIMARY_KEY = "workflow_id"


class DynamoDBMemoryStore:
    """AWS DynamoDB-backed memory store."""

    def __init__(
        self,
        region_name: str,
        table_name: str,
        *,
        endpoint_url: str | None = None,
    ) -> None:
        self.table_name = table_name
        self.region_name = region_name
        client_kwargs = {"region_name": region_name}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        self.dynamodb = boto3.resource("dynamodb", **client_kwargs)
        self.table = self.dynamodb.Table(table_name)

    def ensure_table(self) -> None:
        existing = None
        try:
            existing = self.dynamodb.Table(table_name=self.table_name).table_status
        except ClientError:
            existing = None
        if existing is not None:
            return
        try:
            self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {"AttributeName": _PRIMARY_KEY, "KeyType": "HASH"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": _PRIMARY_KEY, "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
        except ClientError:
            pass

    def save_workflow(self, workflow: WorkflowState) -> None:
        payload = workflow.model_dump(mode="json")
        payload["updated_at"] = payload.get("updated_at") or workflow.updated_at.isoformat()
        self.table.put_item(Item=payload)

    def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        try:
            response = self.table.get_item(Key={_PRIMARY_KEY: workflow_id})
        except ClientError:
            return None
        item = response.get("Item")
        if not item:
            return None
        return WorkflowState.model_validate(item)

    def list_workflows(self) -> list[WorkflowState]:
        workflows: list[WorkflowState] = []
        kwargs = {}
        while True:
            response = self.table.scan(**kwargs)
            for item in response.get("Items", []):
                try:
                    workflows.append(WorkflowState.model_validate(item))
                except Exception:
                    continue
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        workflows.sort(key=lambda workflow: workflow.updated_at, reverse=True)
        return workflows

    def set_long_term_memory(self, key: str, value: str) -> None:
        payload = {
            _PRIMARY_KEY: f"memory::{key}",
            "memory_key": key,
            "memory_value": value,
        }
        self.table.put_item(Item=payload)

    def get_long_term_memory(self, key: str) -> str | None:
        try:
            response = self.table.get_item(Key={_PRIMARY_KEY: f"memory::{key}"})
        except ClientError:
            return None
        item = response.get("Item")
        if not item:
            return None
        return item.get("memory_value")

    def summarize(self):
        workflows = self.list_workflows()
        if not workflows:
            return None
        from app.agent.service import _to_summary

        return _to_summary(workflows[0])


def create_memory_store(settings: Settings):
    backend = (settings.memory_backend or "").lower().strip()
    if backend == "dynamodb":
        return DynamoDBMemoryStore(
            region_name=settings.aws_region,
            table_name=settings.dynamodb_table_name,
        )
    if backend == "local":
        from app.memory.local import LocalMemoryStore

        return LocalMemoryStore(settings.data_dir)
    raise ValueError(f"Unsupported MEMORY_BACKEND: {backend}. Use dynamodb or local.")


def _json_dumps(value) -> str:
    return json.dumps(value)