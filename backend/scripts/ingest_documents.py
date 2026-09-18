import os
import sys
from pathlib import Path

# Ensure the backend package is importable when this script is invoked
# from anywhere (e.g. `python scripts/ingest_documents.py` from the repo root).
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("MEMORY_BACKEND", "local")
os.environ.setdefault("VECTOR_STORE", "in-memory")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_MODEL", "hash:local")

from app.config import get_settings  # noqa: E402
from app.rag.embeddings import LocalHashEmbeddings  # noqa: E402
from app.rag.factory import create_vector_store  # noqa: E402
from app.rag.ingestion import ingest_directory  # noqa: E402

if __name__ == "__main__":
    settings = get_settings()
    documents = BACKEND_ROOT / "documents"
    store = create_vector_store(settings)
    results = ingest_directory(documents, LocalHashEmbeddings(), store)
    total = sum(result["chunks"] for result in results)
    print(f"Ingested {len(results)} documents / {total} chunks from {documents}")