"""Regression tests for the cloud RAG embedding path.

These cover the LangChainEmbeddingsAdapter that lets the app's VectorRetriever
(which calls ``embed([query])``) work with langchain ``OpenAIEmbeddings``
(which only offers ``embed_documents``/``embed_query``). No network calls.
"""

from app.config import Settings
from app.rag.factory import LangChainEmbeddingsAdapter, create_embeddings
from app.rag.embeddings import NVIDIAEmbeddingProvider


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


def test_nvidia_embeddings_use_query_and_passage_modes(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [1.0, 2.0]}]}

    def post(url, *, json, headers, timeout):
        calls.append((url, json))
        return Response()

    monkeypatch.setattr("httpx.post", post)
    settings = Settings(
        embedding_provider="nvidia",
        embedding_model="model-x",
        embedding_model_api="secret",
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_api_key="secret",
    )
    embeddings = create_embeddings(settings)
    assert isinstance(embeddings, NVIDIAEmbeddingProvider)
    assert embeddings.embed_documents(["doc"]) == [[1.0, 2.0]]
    assert embeddings.embed_query("query") == [1.0, 2.0]
    assert calls[0][1]["input_type"] == "passage"
    assert calls[1][1]["input_type"] == "query"
    assert calls[0][0] == "https://integrate.api.nvidia.com/v1/embeddings"
