from fastapi import Depends

from app.agent.service import AgentService
from app.config import Settings, get_settings
from app.llm.provider import LLMProvider, create_llm_provider
from app.memory.interface import MemoryInterface
from app.rag.factory import create_retriever
from app.rag.vector_store import VectorRetriever

# Lambda execution environments are reused across warm invocations. These
# module-level singletons let the LangGraph graph, LLM provider, embedding
# provider, Zilliz client, and memory store be constructed once per warm
# container instead of once per request. Durable workflow state lives in
# DynamoDB/Zilliz, never in process memory, so singleton reuse is safe.
_llm_singleton: LLMProvider | None = None
_retriever_singleton: VectorRetriever | None = None
_memory_singleton: MemoryInterface | None = None
_agent_service_singleton: AgentService | None = None


def _build_llm() -> LLMProvider:
    return create_llm_provider(get_settings())


def _build_retriever() -> VectorRetriever:
    return create_retriever(get_settings())


def _build_memory() -> MemoryInterface:
    from app.memory.dynamodb import create_memory_store

    return create_memory_store(get_settings())


def get_llm(settings: Settings = Depends(get_settings)) -> LLMProvider:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = _build_llm()
    return _llm_singleton


def get_retriever(settings: Settings = Depends(get_settings)) -> VectorRetriever:
    global _retriever_singleton
    if _retriever_singleton is None:
        _retriever_singleton = _build_retriever()
    return _retriever_singleton


def get_memory(settings: Settings = Depends(get_settings)) -> MemoryInterface:
    global _memory_singleton
    if _memory_singleton is None:
        _memory_singleton = _build_memory()
    return _memory_singleton


def get_agent_service(
    llm: LLMProvider = Depends(get_llm),
    retriever: VectorRetriever = Depends(get_retriever),
    memory: MemoryInterface = Depends(get_memory),
) -> AgentService:
    global _agent_service_singleton
    if _agent_service_singleton is None:
        _agent_service_singleton = AgentService(llm=llm, retriever=retriever, memory=memory)
    return _agent_service_singleton


def reset_singletons() -> None:
    """Drop cached singletons. Used by tests and local reload paths."""
    global _llm_singleton, _retriever_singleton, _memory_singleton, _agent_service_singleton
    _llm_singleton = None
    _retriever_singleton = None
    _memory_singleton = None
    _agent_service_singleton = None