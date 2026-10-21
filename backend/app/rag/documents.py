"""Application service for upload extraction and provenance-preserving ingestion."""
from dataclasses import dataclass

from fastapi import HTTPException

from app.rag.ingestion import ingest_text


@dataclass
class IngestedDocument:
    filename: str
    chunks: int


def ingest_upload(file_bytes: bytes, filename: str, workflow_id: str | None, retriever) -> IngestedDocument:
    if filename.lower().endswith(".pdf"):
        try:
            import fitz
            with fitz.open(stream=file_bytes, filetype="pdf") as document:
                pages = [(page.number + 1, page.get_text()) for page in document]
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not read this PDF.") from exc
        chunks = sum(ingest_text(text, filename, "upload", retriever.embeddings, retriever.store, workflow_id=workflow_id, page=page) for page, text in pages if text.strip())
        if not chunks:
            raise HTTPException(status_code=400, detail="This PDF has no extractable text.")
        return IngestedDocument(filename, chunks)
    content = file_bytes.decode("utf-8", errors="ignore")
    if not content.strip():
        raise HTTPException(status_code=400, detail="File is empty or has no extractable text.")
    return IngestedDocument(filename, ingest_text(content, filename, "upload", retriever.embeddings, retriever.store, workflow_id=workflow_id))
