from app.config import Settings
from app.rag.embeddings import LocalHashEmbeddings, NVIDIAEmbeddingProvider
from app.rag.vector_store import InMemoryVectorStore, LocalVectorStore, VectorRetriever


class LangChainEmbeddingsAdapter:
    """Expose langchain embedding objects through the app's ``embed`` contract.

    ``VectorRetriever`` (and the ``EmbeddingsProvider`` protocol) call
    ``embed([query])``; langchain's ``OpenAIEmbeddings`` only offers
    ``embed_documents``/``embed_query``. This adapter bridges the two without
    changing which models/endpoints are used for any provider.
    """

    def __init__(self, embeddings) -> None:
        self._embeddings = embeddings

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings.embed_documents(texts)


def create_embeddings(settings: Settings):
    provider = (settings.embedding_provider or "").lower().strip()

    if provider in {"openai", "openai-compatible", "nvidia"}:
        from langchain_openai import OpenAIEmbeddings

        model = settings.embedding_model
        base_url = settings.resolved_embedding_base_url
        api_key = settings.resolved_embedding_api_key
        if model and base_url and api_key:
            return LangChainEmbeddingsAdapter(
                OpenAIEmbeddings(
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    check_embedding_ctx_length=False,
                    timeout=120,
                )
            )
        if provider == "nvidia" and model and api_key:
            return NVIDIAEmbeddingProvider(
                api_url="https://integrate.api.nvidia.com/v1/embeddings",
                model=model,
                api_key=api_key,
            )

    if provider == "mock":
        return LocalHashEmbeddings()

    model = settings.embedding_model or ""
    if model.startswith("hash:local"):
        return LocalHashEmbeddings()

    raise ValueError(
        "Embedding provider is not configured. Set EMBEDDING_PROVIDER=mock "
        "for offline use or provide model/base_url/api_key for cloud use."
    )


def create_vector_store(settings: Settings):
    backend = (settings.vector_store or "").lower().strip()

    if backend in {"zilliz", "vdb"}:
        from app.rag.zilliz import ZillizVectorStore

        if settings.zilliz_uri and settings.zilliz_token:
            return ZillizVectorStore(
                uri=settings.zilliz_uri,
                token=settings.zilliz_token,
                collection_name=settings.zilliz_collection,
            )
        raise ValueError(
            "ZILLIZ_URI and ZILLIZ_TOKEN are required when VECTOR_STORE=zilliz."
        )

    if backend == "in-memory":
        return InMemoryVectorStore()

    raise ValueError(f"Unsupported VECTOR_STORE: {backend}. Use zilliz or in-memory.")


def create_retriever(settings: Settings) -> VectorRetriever:
    embeddings = create_embeddings(settings)
    store = create_vector_store(settings)
    return VectorRetriever(store, embeddings)


def create_local_vector_store(settings: Settings) -> LocalVectorStore:
    path = settings.data_dir / "vectors.json"
    return LocalVectorStore(str(path))