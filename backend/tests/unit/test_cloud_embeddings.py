"""Regression tests for the cloud RAG embedding path.

These cover the LangChainEmbeddingsAdapter that lets the app's VectorRetriever
(which calls ``embed([query])``) work with langchain ``OpenAIEmbeddings``
(which only offers ``embed_documents``/``embed_query``). No network calls.
"""

from app.config import Settings
from app.rag.factory import LangChainEmbeddingsAdapter, create_embeddings


class _FakeLangChainEmbeddings:
    """Mimics the langchain OpenAIEmbeddings surface used in create_embeddings."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


def test_adapter_satisfies_embed_contract_without_openai_install():
    fake = _FakeLangChainEmbeddings()
    adapter = LangChainEmbeddingsAdapter(fake)
    assert adapter.embed(["abc", "de"]) == [[3.0], [2.0]]


def test_retriever_accepts_adapter_powered_store(tmp_path):
    from app.rag.vector_store import LocalVectorStore, VectorRetriever

    store = LocalVectorStore(tmp_path / "vectors.json")
    retriever = VectorRetriever(store, LangChainEmbeddingsAdapter(_FakeLangChainEmbeddings()))
    store.add(
        "some content",
        {"source": "cloud.md", "document_type": "md"},
        [7.0],
    )
    evidence = retriever.retrieve("query-ish", limit=1)
    assert evidence and evidence[0].source == "cloud.md"


def test_create_embeddings_returns_adapter_for_cloud_provider(monkeypatch):
    monkeypatch.setattr(
        "langchain_openai.OpenAIEmbeddings",
        _FakeLangChainEmbeddings,
    )
    settings = Settings(
        embedding_provider="nvidia",
        embedding_model="model-x",
        embedding_model_api="secret",
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_api_key="secret",
    )
    embeddings = create_embeddings(settings)
    assert isinstance(embeddings, LangChainEmbeddingsAdapter)
    assert embeddings.embed(["hi"]) == [[2.0]]