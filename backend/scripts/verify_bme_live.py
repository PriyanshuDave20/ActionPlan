"""Live verification: BME 415 document drives a grounded plan via real NVIDIA.

Uses real NVIDIA LLM and real Zilliz retrieval; memory backend follows the
environment (DynamoDB if configured, local otherwise).

Run: py -3 scripts/verify_bme_live.py
"""
import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# Use local memory unless the caller explicitly wants the real backend:
# avoids DynamoDB clock-skew failures on machines with drifted clocks.
if not os.environ.get("BME_USE_DYNAMODB"):
    os.environ["MEMORY_BACKEND"] = "local"
    os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="bme-live-"))

from fastapi.testclient import TestClient  # noqa: E402
from app.agent.service import AgentService  # noqa: E402
from app.api.dependencies import get_agent_service, get_retriever, get_workspace  # noqa: E402
from app.llm.provider import create_llm_provider  # noqa: E402
from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.rag.factory import create_retriever  # noqa: E402
from app.workspace import WorkspaceStore  # noqa: E402

settings = get_settings()
retriever = create_retriever(settings)
llm = create_llm_provider(settings)
from app.memory.dynamodb import create_memory_store  # noqa: E402
memory = create_memory_store(settings)
workspace = WorkspaceStore(settings.resolved_workspace_db_path)

service = AgentService(llm, retriever, memory)
app.dependency_overrides[get_agent_service] = lambda: service
app.dependency_overrides[get_retriever] = lambda: retriever
app.dependency_overrides[get_workspace] = lambda: workspace

try:
    client = TestClient(app)
    goal = "Compare KHDRBS2 wild-type and R168C RNA-binding behaviour using easyCLIP data"
    created = client.post("/goals?sync=true", json={"goal": goal, "priority": "high"})
    assert created.status_code == 201, created.text[:300]
    wf_id = created.json()["workflow_id"]
    print(f"created: {wf_id}")

    doc = (BACKEND_ROOT / "documents" / "bme415_proposal.txt").read_bytes()
    ingested = client.post(
        "/documents/ingest",
        files={"file": ("bme415_proposal.txt", doc, "text/plain")},
        data={"workflow_id": wf_id},
    )
    assert ingested.status_code == 200, ingested.text[:300]
    print(f"ingested: {ingested.json()}")

    refreshed = client.post(f"/workflows/{wf_id}/refresh")
    assert refreshed.status_code == 200, refreshed.text[:500]
    body = refreshed.json()

    spec = body.get("project_specification") or {}
    print(f"project_type: {spec.get('project_type')}")
    print(f"title: {spec.get('title', '')[:80]}")

    tasks = body.get("tasks") or []
    plan_text = " ".join(((t.get("title") or "") + " " + t.get("description", "")).lower() for t in tasks)
    print(f"tasks: {len(tasks)}")
    for t in tasks:
        print(f"  - {t.get('title') or t.get('description')}")

    grounded_terms = ["r168c", "binding", "khdrbs2", "motif", "transcript"]
    hits = [term for term in grounded_terms if term in plan_text]
    print(f"grounded terms found: {hits}")
    assert hits, "plan is not grounded in the BME document"
    assert "governing organizational policies" not in plan_text
    assert len(tasks) >= 3, "plan should have document-derived tasks"

    blocked = body.get("detected_blockers") or []
    recommendation = body.get("recommendation") or {}
    print(f"recommendation: {recommendation.get('action')} -> {recommendation.get('affected_task')}")
    print(f"reason: {recommendation.get('reason', '')[:200]}")
    print("\nLIVE BME VERIFICATION PASSED")
finally:
    app.dependency_overrides.clear()
