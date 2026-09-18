import json
import math
from typing import Any, Protocol

from app.models.evidence import Evidence
from app.rag.embeddings import EmbeddingsProvider


class VectorStore(Protocol):
    def add(self, content: str, metadata: dict[str, Any], embedding: list[float]) -> None:
        ...

    def search(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[Evidence]:
        ...


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def add(self, content: str, metadata: dict[str, Any], embedding: list[float]) -> None:
        self.records.append(
            {"embedding": embedding, "content": content, "metadata": metadata}
        )

    def search(self, embedding: list[float], limit: int = 5) -> list[Evidence]:
        scored = [
            (_cosine_similarity(embedding, record["embedding"]), record)
            for record in self.records
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            Evidence(
                content=record["content"],
                metadata=record["metadata"],
                **record["metadata"],
            )
            for _, record in scored[:limit]
        ]


class LocalVectorStore:
    """JSON-persisted vector store for offline development and tests."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                self.records = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            self.records = []

    def _persist(self) -> None:
        import os

        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self.records, handle)

    def add(self, content: str, metadata: dict[str, Any], embedding: list[float]) -> None:
        self.records.append(
            {"embedding": embedding, "content": content, "metadata": metadata}
        )
        self._persist()

    def search(self, embedding: list[float], limit: int = 5) -> list[Evidence]:
        scored = [
            (_cosine_similarity(embedding, record["embedding"]), record)
            for record in self.records
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            Evidence(content=record["content"], metadata=record["metadata"], **record["metadata"])
            for _, record in scored[:limit]
        ]


class VectorRetriever:
    def __init__(self, store: VectorStore, embeddings: EmbeddingsProvider) -> None:
        self.store = store
        self.embeddings = embeddings

    def retrieve(self, query: str, limit: int = 5) -> list[Evidence]:
        embedding = self.embeddings.embed([query])[0]
        return self.store.search(embedding, limit=limit)