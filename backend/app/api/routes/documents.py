from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies import get_retriever
from app.models.workflow import IngestResponse
from app.rag.ingestion import ingest_text
from app.rag.vector_store import VectorRetriever

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document_route(
    file: UploadFile = File(...),
    retriever: VectorRetriever = Depends(get_retriever),
) -> IngestResponse:
    content = (await file.read()).decode("utf-8", errors="ignore")
    if not content.strip():
        raise HTTPException(status_code=400, detail="File is empty.")
    chunk_count = ingest_text(
        content,
        source=file.filename or "upload.txt",
        document_type="upload",
        embeddings=retriever.embeddings,
        store=retriever.store,
    )
    return IngestResponse(filename=file.filename or "upload.txt", chunks=chunk_count)