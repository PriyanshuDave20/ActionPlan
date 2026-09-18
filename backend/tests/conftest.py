import pytest

from app.config import Settings
from app.llm.provider import MockLLMProvider
from app.memory.local import LocalMemoryStore
from app.rag.embeddings import LocalHashEmbeddings
from app.rag.vector_store import LocalVectorStore, VectorRetriever


@pytest.fixture
def components(tmp_path):
    settings = Settings(data_dir=tmp_path, embedding_model="hash:local")
    memory = LocalMemoryStore(tmp_path)
    store = LocalVectorStore(tmp_path / "vectors.json")
    retriever = VectorRetriever(store, LocalHashEmbeddings())
    return MockLLMProvider(), retriever, memory, store
