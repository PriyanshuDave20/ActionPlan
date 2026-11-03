"""AWS Lambda worker handler for async workflow execution.

This handler is invoked by SQS queue messages containing workflow IDs.
It claims the workflow and executes the LangGraph workflow asynchronously.
"""

import json
import logging
import os

from app.agent.service import (
    AgentService,
    WorkflowNotFoundError,
)
from app.memory.dynamodb import create_memory_store
from app.config import get_settings, validate_settings
from app.models.work_request import WorkRequestInput

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize settings
settings = get_settings()
validate_settings(settings)

# Initialize dependencies (singletons for warm Lambda invocations)
_memory_singleton = None
_retriever_singleton = None
_llm_singleton = None
_agent_service_singleton = None


def _get_memory():
    global _memory_singleton
    if _memory_singleton is None:
        _memory_singleton = create_memory_store(settings)
    return _memory_singleton


def _get_agent_service():
    global _agent_service_singleton
    if _agent_service_singleton is None:
        from app.llm.provider import create_llm_provider
        from app.rag.factory import create_retriever
        
        llm = create_llm_provider(settings)
        retriever = create_retriever(settings)
        memory = _get_memory()
        _agent_service_singleton = AgentService(llm=llm, retriever=retriever, memory=memory)
    return _agent_service_singleton


def handler(event, context):
    """SQS message handler for workflow execution.

    Expected message body:
    {"workflow_id": "wf_xxx", "payload": {...WorkRequestInput...}}

    Failure policy (matches the queue's ReportBatchItemFailures +
    redrive-to-DLQ configuration):
    - Transient execution errors are reported via ``batchItemFailures`` so
      SQS retries the delivery; the workflow is persisted as FAILED by the
      service before this happens.
    - Permanent problems (malformed message, missing workflow record) are
      acknowledged without retry — retrying could never succeed.
    - Duplicate deliveries (workflow no longer QUEUED) are acknowledged as
      idempotent skips.
    """
    records = event.get("Records", [])
    logger.info("Received event with %d records", len(records))

    results = []
    batch_item_failures = []

    for record in records:
        message_id = record.get("messageId", "")
        try:
            body = json.loads(record.get("body", "{}"))
        except json.JSONDecodeError as exc:
            logger.error("Record %s has invalid JSON body: %s", message_id, exc)
            results.append({"message_id": message_id, "status": "error", "permanent": True, "error": "invalid message body"})
            continue  # permanent: acknowledge, never retry

        workflow_id = body.get("workflow_id")
        if not workflow_id:
            logger.error("Record %s missing workflow_id", message_id)
            results.append({"message_id": message_id, "status": "error", "permanent": True, "error": "missing workflow_id"})
            continue  # permanent: acknowledge, never retry

        raw_payload = body.get("payload")
        try:
            payload = WorkRequestInput.model_validate(raw_payload) if raw_payload else None
        except Exception as exc:
            logger.error("Record %s has invalid payload for %s: %s", message_id, workflow_id, exc)
            results.append({"workflow_id": workflow_id, "message_id": message_id, "status": "error", "permanent": True, "error": "invalid payload"})
            continue  # permanent: acknowledge, never retry

        logger.info("Processing workflow %s", workflow_id)

        try:
            service = _get_agent_service()
            result = service.execute_queued_workflow(workflow_id, payload)
        except WorkflowNotFoundError as exc:
            logger.error("Workflow %s missing from persistent memory: %s", workflow_id, exc)
            results.append({"workflow_id": workflow_id, "message_id": message_id, "status": "error", "permanent": True, "error": "workflow record not found"})
            continue  # permanent: acknowledge, never retry
        except Exception as exc:  # transient execution failure (already persisted as FAILED)
            logger.exception("Transient failure executing workflow %s", workflow_id)
            results.append({"workflow_id": workflow_id, "message_id": message_id, "status": "error", "permanent": False, "error": str(exc)})
            batch_item_failures.append({"itemIdentifier": message_id})
            continue

        if result is not None:
            logger.info("Workflow %s finished with state %s", workflow_id, result.execution_state.value)
            results.append({"workflow_id": workflow_id, "message_id": message_id, "status": "success", "execution_state": result.execution_state.value})
        else:
            logger.info("Workflow %s not claimable (duplicate delivery or already running); skipping.", workflow_id)
            results.append({"workflow_id": workflow_id, "message_id": message_id, "status": "skipped", "reason": "not_queued_or_already_running"})

    return {
        "statusCode": 200,
        "body": json.dumps({"results": results}),
        "batchItemFailures": batch_item_failures,
    }


def local_test():
    """Test function for local development."""
    # Set up local environment
    os.environ.setdefault("MEMORY_BACKEND", "local")
    os.environ.setdefault("VECTOR_STORE", "in-memory")
    os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
    os.environ.setdefault("LLM_PROVIDER", "mock")
    os.environ.setdefault("DATA_DIR", "/tmp/actionplan-test")
    
    from app.memory.local import LocalMemoryStore
    from app.llm.provider import MockLLMProvider
    from app.rag.embeddings import LocalHashEmbeddings
    from app.rag.vector_store import LocalVectorStore, VectorRetriever
    from pathlib import Path
    
    # Create test workflow
    from app.models.workflow import WorkflowState, WorkflowExecutionState
    from app.models.work_request import WorkRequestInput
    from uuid import uuid4
    from app.agent.service import AgentService
    from app.memory.local import LocalMemoryStore
    from app.llm.provider import MockLLMProvider
    from app.rag.embeddings import LocalHashEmbeddings
    from app.rag.vector_store import LocalVectorStore, VectorRetriever
    from app.config import Settings
    from tempfile import TemporaryDirectory
    
    with TemporaryDirectory() as tmp:
        settings = Settings(data_dir=tmp, embedding_model="hash:local")
        memory = LocalMemoryStore(tmp)
        store = LocalVectorStore(tmp / "vectors.json")
        retriever = VectorRetriever(store, LocalHashEmbeddings())
        llm = MockLLMProvider()
        
        service = AgentService(llm, retriever, memory)
        
        # Create a test workflow
        workflow = service.create_workflow(WorkRequestInput(goal="Test async workflow"))
        print(f"Created workflow: {workflow.workflow_id}, state: {workflow.execution_state.value}")
        
        # Wait for background execution to complete
        import time
        for _ in range(30):
            time.sleep(0.5)
            wf = service.get_workflow(workflow.workflow_id)
            if wf and wf.execution_state.value in ("completed", "failed"):
                print(f"Workflow finished: {wf.execution_state.value}")
                if wf.execution_error:
                    print(f"Error: {wf.execution_error}")
                break
        else:
            print("Timeout waiting for workflow completion")


if __name__ == "__main__":
    local_test()