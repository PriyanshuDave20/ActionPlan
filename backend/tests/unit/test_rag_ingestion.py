from pathlib import Path

from app.rag.embeddings import LocalHashEmbeddings
from app.rag.factory import create_retriever
from app.rag.ingestion import chunk_text, ingest_document
from app.config import Settings


def test_chunk_text_does_not_overlap_past_end():
    assert chunk_text("abcdefghij", chunk_size=5, overlap=1) == ["abcde", "efghi", "ij"]


def test_chunk_text_empty_string():
    assert chunk_text("   ") == []


def test_ingest_document_text(tmp_path):
    source = tmp_path / "procedure.txt"
    source.write_text("Every change must be reviewed by a manager before merging.", encoding="utf-8")
    embeddings = LocalHashEmbeddings()
    from app.rag.vector_store import LocalVectorStore

    store = LocalVectorStore(tmp_path / "vectors.json")
    result = ingest_document(source, embeddings, store, chunk_size=32)
    assert result["filename"] == "procedure.txt"
    assert result["chunks"] >= 1
    assert store.records


def test_ingest_document_missing_returns_error(tmp_path):
    embeddings = LocalHashEmbeddings()
    from app.rag.vector_store import LocalVectorStore

    store = LocalVectorStore(tmp_path / "vectors.json")
    missing = tmp_path / "missing.txt"
    with __import__("pytest").raises(FileNotFoundError):
        ingest_document(missing, embeddings, store)


def test_upper_chunk_and_overlap():
    text = "".join("x" for _ in range(10)) + "y"
    chunks = chunk_text(text, chunk_size=4, overlap=2)
    assert len(chunks) >= 3
    assert "".join(chunks).count("y") >= 1