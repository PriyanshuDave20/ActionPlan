import hashlib
from typing import Protocol

import httpx


class EmbeddingsProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class LocalHashEmbeddings:
    """Deterministic local embeddings for offline development and tests."""

    def __init__(self, embedding_size: int = 256) -> None:
        self.embedding_size = embedding_size

    def embed(self, texts: str | list[str]) -> list[float] | list[list[float]]:
        single = isinstance(texts, str)
        items = [texts] if single else texts
        vectors: list[list[float]] = []
        for text in items:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [float(byte) / 255.0 for byte in digest]
            while len(vector) < self.embedding_size:
                vector.extend([0.0] * (self.embedding_size - len(vector)))
            vectors.append(vector[: self.embedding_size])
        return vectors[0] if single else vectors


class NVIDIAEmbeddingProvider:
    """Embeddings served by an NVIDIA NIM / OpenAI-compatible endpoint."""

    def __init__(self, api_url: str, model: str, api_key: str) -> None:
        self.api_url = api_url
        self.model = model
        self.api_key = api_key

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model, "input": texts, "input_type": input_type}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = httpx.post(self.api_url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        vectors = [item["embedding"] for item in data["data"]]
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"NVIDIA embeddings returned {len(vectors)} vectors for {len(texts)} inputs."
            )
        return vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Default to passage mode for backward-compatible indexing calls."""
        return self._embed(texts, input_type="passage")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, input_type="passage")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], input_type="query")[0]
