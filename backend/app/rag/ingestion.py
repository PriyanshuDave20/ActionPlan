from pathlib import Path

from app.config import Settings
from app.rag.embeddings import EmbeddingsProvider
from app.rag.vector_store import VectorStore


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 48) -> list[str]:
    """Split text into overlapping chunks of up to chunk_size characters."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


class Chunker:
    def __init__(self, chunk_size: int = 512, overlap: int = 48) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        return chunk_text(text, self.chunk_size, self.overlap)


def ingest_text(
    text: str,
    source: str,
    document_type: str,
    embeddings: EmbeddingsProvider,
    store: VectorStore,
    chunk_size: int = 512,
    overlap: int = 48,
) -> int:
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    vectors = embeddings.embed(chunks)
    for chunk, vector in zip(chunks, vectors):
        store.add(
            chunk,
            {"source": source, "page": 0, "document_type": document_type},
            vector,
        )
    return len(chunks)


def ingest_document(
    path: Path,
    embeddings: EmbeddingsProvider,
    store: VectorStore,
    chunk_size: int = 512,
    overlap: int = 48,
    include_chunks: bool = False,
) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import fitz

        document = fitz.open(str(path))
        full_text = "\n\n".join(page.get_text() for page in document)
        document_type = "pdf"
    else:
        full_text = path.read_text(encoding="utf-8", errors="ignore")
        document_type = "text"

    chunks = chunk_text(full_text, chunk_size=chunk_size, overlap=overlap)
    vectors = embeddings.embed(chunks)
    for chunk, vector in zip(chunks, vectors):
        store.add(
            chunk,
            {"source": path.name, "page": 0, "document_type": document_type},
            vector,
        )

    result = {
        "filename": path.name,
        "chunks": len(chunks),
    }
    if include_chunks:
        result["text_chunks"] = chunks
    return result


def ingest_directory(
    directory: Path,
    embeddings: EmbeddingsProvider = None,
    store: VectorStore = None,
    settings: Settings = None,
) -> list[dict]:
    if settings is not None and embeddings is None:
        from app.rag.factory import create_embeddings

        embeddings = create_embeddings(settings)
    results: list[dict] = []
    if embeddings is None or store is None:
        return results
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in {".pdf", ".txt", ".md"}:
            results.append(ingest_document(path, embeddings, store))
    return results