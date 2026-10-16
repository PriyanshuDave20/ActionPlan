from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service, get_retriever
from app.models.workflow import IngestResponse
from app.rag.ingestion import ingest_text
from app.rag.vector_store import VectorRetriever

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document_route(
    file: UploadFile = File(...),
    workflow_id: str | None = Form(default=None),
    service: AgentService = Depends(get_agent_service),
    retriever: VectorRetriever = Depends(get_retriever),
) -> IngestResponse:
    workflow = None
    if workflow_id:
        workflow = service.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    filename = file.filename or "upload.txt"
    file_bytes = await file.read()
    if filename.lower().endswith(".pdf"):
        try:
            import fitz

            with fitz.open(stream=file_bytes, filetype="pdf") as document:
                content = "\n\n".join(page.get_text() for page in document)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not read this PDF.") from exc
    else:
        content = file_bytes.decode("utf-8", errors="ignore")
    if not content.strip():
        raise HTTPException(status_code=400, detail="File is empty.")
    chunk_count = ingest_text(
        content,
        source=filename,
        document_type="upload",
        embeddings=retriever.embeddings,
        store=retriever.store,
        workflow_id=workflow_id,
    )
    if workflow is not None:
        documents = list(workflow.execution_metadata.get("documents", []))
        if filename not in documents:
            documents.append(filename)
        workflow.execution_metadata["documents"] = documents
        service.memory.save_workflow(workflow)
    return IngestResponse(filename=filename, chunks=chunk_count)
