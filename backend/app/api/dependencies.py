from fastapi import Depends

from app.agent.service import AgentService
from app.config import Settings, get_settings
from app.llm.provider import LLMProvider, create_llm_provider
from app.memory.interface import MemoryInterface
from app.rag.factory import create_retriever
from app.rag.vector_store import VectorRetriever


def get_llm(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return create_llm_provider(settings)


def get_retriever(settings: Settings = Depends(get_settings)) -> VectorRetriever:
    return create_retriever(settings)


def get_memory(settings: Settings = Depends(get_settings)) -> MemoryInterface:
    from app.memory.dynamodb import create_memory_store

    return create_memory_store(settings)


def get_agent_service(
    llm: LLMProvider = Depends(get_llm),
    retriever: VectorRetriever = Depends(get_retriever),
    memory: MemoryInterface = Depends(get_memory),
) -> AgentService:
    return AgentService(llm=llm, retriever=retriever, memory=memory)