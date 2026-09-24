from typing import Any

from app.models.evidence import Evidence


class ZillizVectorStore:
    """Zilliz Cloud (Milvus) backed vector store."""

    DIMENSION = 2048

    def __init__(
        self,
        uri: str,
        token: str,
        collection_name: str,
        dimension: int = DIMENSION,
    ) -> None:
        self.uri = uri
        self.token = token
        self.collection_name = collection_name
        self.dimension = dimension
        self._client = None
        self._connect()

    def _connect(self) -> None:
        from pymilvus import MilvusClient

        self._client = MilvusClient(uri=self.uri, token=self.token)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        from pymilvus import DataType, FieldSchema, CollectionSchema

        if self._client.has_collection(self.collection_name):
            self._ensure_index()
            self._ensure_loaded()
            return
        schema = CollectionSchema(
            fields=[
                FieldSchema("id", DataType.VARCHAR, max_length=64, is_primary=True),
                FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=self.dimension),
                FieldSchema("content", DataType.VARCHAR, max_length=8192),
                FieldSchema("source", DataType.VARCHAR, max_length=512),
                FieldSchema("page", DataType.INT64),
                FieldSchema("document_type", DataType.VARCHAR, max_length=128),
            ]
        )
        self._client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
        )
        self._ensure_index()
        self._ensure_loaded()

    def _ensure_index(self) -> None:
        """Zilliz Cloud loads collections only after a vector index exists;
        AUTOINDEX picks the default index type per dimension."""
        index_info = self._client.list_indexes(self.collection_name)
        if not index_info:
            from pymilvus.milvus_client.index import IndexParams

            index_params = IndexParams()
            index_params.add_index(
                field_name="embedding",
                index_type="AUTOINDEX",
                metric_type="COSINE",
            )
            self._client.create_index(
                collection_name=self.collection_name,
                index_params=index_params,
                timeout=120,
            )

    def _ensure_loaded(self) -> None:
        """Milvus/Zilliz searches only run against collections loaded into
        memory. Newly created or previously loaded collections may not be
        loaded yet, so load idempotently before any search."""
        try:
            from pymilvus import utility

            from pymilvus.milvus_client import connections

            conn = connections.get_connection(self._client.conn_name)
            state = utility.load_state(self.collection_name, using=conn)
            if state != "Loaded":
                self._client.load_collection(self.collection_name)
        except Exception:
            # load_state may not exist across pymilvus versions; loading twice
            # is harmless, so fall back to a direct, idempotent load.
            self._client.load_collection(self.collection_name)

    def add(self, content: str, metadata: dict[str, Any], embedding: list[float]) -> None:
        import uuid

        record = {
            "id": uuid.uuid4().hex,
            "embedding": embedding[: self.dimension]
            + [0.0] * max(0, self.dimension - len(embedding)),
            "content": content,
            "source": metadata.get("source", ""),
            "page": metadata.get("page", 1),
            "document_type": metadata.get("document_type", "unknown"),
        }
        self._client.insert(self.collection_name, [record])

    def search(self, embedding: list[float], limit: int = 5) -> list[Evidence]:
        results = self._client.search(
            collection_name=self.collection_name,
            data=[embedding[: self.dimension]],
            anns_field="embedding",
            limit=limit,
            output_fields=["content", "source", "page", "document_type"],
        )
        evidence: list[Evidence] = []
        for hits in results:
            for hit in hits:
                entity = hit.get("entity", {})
                evidence.append(
                    Evidence(
                        content=entity.get("content", ""),
                        source=entity.get("source", ""),
                        page=entity.get("page", 1),
                        document_type=entity.get("document_type", "unknown"),
                    )
                )
        return evidence