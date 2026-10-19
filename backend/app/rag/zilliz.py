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
        database_name: str = "default",
    ) -> None:
        self.uri = uri
        self.token = token
        self.collection_name = collection_name
        self.database_name = database_name
        self.dimension = dimension
        self._client = None
        self._connect()

    def _connect(self) -> None:
        from pymilvus import MilvusClient

        client = MilvusClient(
            uri=self.uri,
            token=self.token,
            db_name=self.database_name,
        )
        # Existing deployments may have their collection in a named database
        # while older configuration only specifies the cluster and collection.
        # Find that collection before _ensure_collection can create a duplicate
        # in the default database.
        if (
            self.database_name == "default"
            and not client.has_collection(self.collection_name)
        ):
            for database_name in client.list_databases():
                if database_name == "default":
                    continue
                candidate = MilvusClient(
                    uri=self.uri,
                    token=self.token,
                    db_name=database_name,
                )
                if candidate.has_collection(self.collection_name):
                    self.database_name = database_name
                    client = candidate
                    break
        self._client = client
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
            index_params = self._client.prepare_index_params()
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
        """Use the MilvusClient API to ensure the collection is queryable."""
        state = self._client.get_load_state(self.collection_name).get("state")
        state_name = getattr(state, "name", str(state)).lower()
        if state_name != "loaded":
            self._client.load_collection(self.collection_name)

    def add(self, content: str, metadata: dict[str, Any], embedding: list[float]) -> None:
        import uuid

        if len(embedding) != self.dimension:
            raise ValueError(
                f"Embedding dimension {len(embedding)} does not match Milvus collection "
                f"dimension {self.dimension}. Use the same embedding model for indexing and search."
            )
        record = {
            "id": uuid.uuid4().hex,
            "embedding": embedding,
            "content": content,
            "source": metadata.get("source", ""),
            "page": metadata.get("page", 1),
            "document_type": metadata.get("document_type", "unknown"),
        }
        self._client.insert(self.collection_name, [record])


    def search(
        self,
        embedding: list[float],
        limit: int = 5,
        workflow_id: str | None = None,
    ) -> list[Evidence]:
        if len(embedding) != self.dimension:
            raise ValueError(
                f"Embedding dimension {len(embedding)} does not match Milvus collection "
                f"dimension {self.dimension}. Use the same embedding model for indexing and search."
            )

        search_filter = ""
        if workflow_id is not None:
            # Escape LIKE wildcards so workflow IDs containing underscores do
            # not match another project's namespace.
            prefix = (
                workflow_id.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            search_filter = (
                f'(source like r"{prefix}::%" or '
                'not (source like r"%::%"))'
            )

        results = self._client.search(
            collection_name=self.collection_name,
            data=[embedding],
            anns_field="embedding",
            limit=limit,
            output_fields=["content", "source", "page", "document_type"],
            filter=search_filter,
        )

        evidence: list[Evidence] = []

        for hits in results:
            for hit in hits:
                entity = hit.get("entity", {})
                source = str(entity.get("source", ""))
                if workflow_id is not None and source.startswith(f"{workflow_id}::"):
                    source = source[len(workflow_id) + 2 :]

                evidence.append(
                    Evidence(
                        content=entity.get("content", ""),
                        source=source,
                        page=entity.get("page", 1),
                        document_type=entity.get(
                            "document_type", "unknown"
                        ),
                    )
                )

        return evidence
