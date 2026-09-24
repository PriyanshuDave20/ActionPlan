"""Measure real POST /goals latency through the existing LangGraph workflow.

Uses the REAL cloud stack configured in backend/.env (NVIDIA LLM +
embeddings, Zilliz vector store, DynamoDB memory, LangSmith optional). It
times the major phases and the full workflow so we can decide whether the
synchronous API can stay within API Gateway HTTP API's 30-second limit.

This script makes real paid cloud calls. Only run it when backend/.env has
working credentials. Offline stacks (mock/in-memory/local) are measured too,
but mean nothing for the 30-second API Gateway question.

Usage:
    py -3 scripts/measure_goals_latency.py [--goal "Goal text"]
"""

import argparse
import sys
import time
from contextlib import contextmanager
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import httpx  # noqa: E402


@contextmanager
def timed(label: str):
    start = time.perf_counter()
    try:
        yield
        elapsed = time.perf_counter() - start
        print(f"  {label:<45} {elapsed:8.3f} s")
    except Exception as error:  # noqa: BLE001
        elapsed = time.perf_counter() - start
        print(f"  {label:<45} {elapsed:8.3f} s  ERROR: {type(error).__name__}: {error}")
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default="Prepare Project Alpha for production")
    args = parser.parse_args()

    import os

    from app.config import get_settings

    settings = get_settings()
    print(f"Stack: LLM={settings.llm_provider} embedding={settings.embedding_provider} "
          f"vector={settings.vector_store} memory={settings.memory_backend} "
          f"tracing={settings.langchain_tracing_v2}")

    llm = retriever = memory = service = None

    # LLM provider construction + a representative typed extraction.
    try:
        from app.llm.provider import create_llm_provider
        with timed("LLM provider construction"):
            llm = create_llm_provider(settings)

        from app.models.work_request import WorkRequest
        work_request = WorkRequest(goal=args.goal)
        with timed("LLM analyze_objective call"):
            llm.analyze_objective(work_request)
        with timed("LLM extract_procedures call"):
            llm.extract_procedures(work_request)
        with timed("LLM extract_requirements call"):
            llm.extract_requirements(work_request)
    except Exception as error:
        print(f"LLM phase unavailable (POST /goals cannot complete without it): {error}")
    else:
        pass

    # Embeddings + Zilliz.
    try:
        from app.rag.factory import create_retriever
        with timed("Embedding+Zilliz retriever construction"):
            retriever = create_retriever(settings)
        with timed("Embedding + Zilliz retrieve (5 docs)"):
            evidence = retriever.retrieve("security review requirements", limit=5)
            print(f"      -> {len(evidence)} evidence items")
    except Exception as error:
        print(f"RAG/embedding phase unavailable: {error}")

    # DynamoDB memory.
    try:
        from app.memory.dynamodb import create_memory_store
        with timed("DynamoDB memory store construction"):
            memory = create_memory_store(settings)
        if memory is not None:
            with timed("DynamoDB list_workflows (scan)"):
                memory.list_workflows()
    except Exception as error:
        print(f"DynamoDB phase unavailable: {error}")

    # Full workflow (this is the POST /goals equivalent).
    try:
        from app.agent.service import AgentService
        with timed("AgentService + LangGraph build"):
            service = AgentService(llm=llm, retriever=retriever, memory=memory)
    except Exception as error:
        service = None
        print(f"AgentService construction unavailable: {error}")

    if service is not None:
        start = time.perf_counter()
        try:
            workflow = service.create_workflow(args.goal)
            elapsed = time.perf_counter() - start
            print(f"\nPOST /goals equivalent (full LangGraph workflow): {elapsed:8.3f} s")
            print(f"      workflow_id={workflow.workflow_id} tasks={len(workflow.tasks)}")
            limit = 30
            print(f"      -> Within API Gateway 30 s limit: {'YES' if elapsed < limit else 'NO — async architecture required'}")
        except Exception as error:  # noqa: BLE001
            elapsed = time.perf_counter() - start
            print(f"Full workflow failed after {elapsed:.3f} s: {type(error).__name__}: {error}")


if __name__ == "__main__":
    main()