from app.models.workflow import WorkflowState
from app.rag.embeddings import LocalHashEmbeddings
from app.rag.ingestion import chunk_text


def test_chunks_are_nonempty_and_retrieval_metadata_is_preserved(tmp_path):
    assert chunk_text("abcdefghij", chunk_size=5, overlap=1) == ["abcde", "efghi", "ij"]
    from app.rag.vector_store import LocalVectorStore, VectorRetriever

    store = LocalVectorStore(tmp_path / "vectors.json")
    embeddings = LocalHashEmbeddings()
    store.add("security review is required", {"source": "policy.pdf", "page": 4, "document_type": "pdf"}, embeddings.embed("security review"))
    evidence = VectorRetriever(store, embeddings).retrieve("security review")
    assert evidence[0].source == "policy.pdf"
    assert evidence[0].page == 4


def test_memory_round_trip_and_workflow_isolation(tmp_path):
    from app.memory.local import LocalMemoryStore

    memory = LocalMemoryStore(tmp_path)
    first = WorkflowState(workflow_id="one", original_goal="First")
    second = WorkflowState(workflow_id="two", original_goal="Second")
    memory.save_workflow(first)
    memory.save_workflow(second)
    assert memory.get_workflow("one").original_goal == "First"
    assert memory.get_workflow("two").original_goal == "Second"
