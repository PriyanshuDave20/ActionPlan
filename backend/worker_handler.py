"""AWS Lambda worker handler for async workflow execution.

This handler is invoked by SQS queue messages containing workflow IDs.
It claims the workflow and executes the LangGraph workflow asynchronously.
"""

import json
import logging
import os

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service, reset_singletons
from app.memory.dynamodb import create_memory_store
from app.config import get_settings, validate_settings

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
    
    Expected event format:
    {
        "Records": [
            {
                "body": "{\"workflow_id\": \"wf_xxx\", \"payload\": {\"goal\": \"...\"}}"
            }
        ]
    }
    """
    logger.info(f"Received event with {len(event.get('Records', []))} records")
    
    results = []
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            workflow_id = body.get("workflow_id")
            if not workflow_id:
                logger.error(f"Record missing workflow_id: {record}")
                results.append({"workflow_id": None, "status": "error", "error": "Missing workflow_id"})
                continue
            
            logger.info(f"Processing workflow {workflow_id}")
            
            # Get agent service and execute
            service = _get_agent_service()
            result = service.execute_queued_workflow(workflow_id)
            
            if result:
                logger.info(f"Workflow {workflow_id} completed with state: {result.execution_state.value}")
                results.append({"workflow_id": workflow_id, "status": "success", "execution_state": result.execution_state.value})
            else:
                logger.warning(f"Workflow {workflow_id} could not be claimed (already running or not queued)")
                results.append({"workflow_id": workflow_id, "status": "skipped", "reason": "not_queued_or_already_running"})
                
        except Exception as e:
            logger.exception(f"Error processing record: {e}")
            results.append({"workflow_id": body.get("workflow_id") if "body" in locals() else None, "status": "error", "error": str(e)})
    
    return {
        "statusCode": 200,
        "body": json.dumps({"results": results})
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