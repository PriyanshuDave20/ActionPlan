# AI Workplace Operations Agent - Backend

FastAPI + LangGraph backend for the workplace operations agent. Turns a goal into a validated action plan: analyze objective -> extract requirements/procedures -> collect evidence -> plan -> validate (bounded revision) -> optimize critical path -> detect blockers -> recommend next action -> persist memory.

## Run

```powershell
py -3 -m pip install -e ".[test]"
py -3 scripts/run_api.py        # serves http://127.0.0.1:8000, offline mock stack by default
```

`run_api.py` sets sensible offline defaults (mock LLM/embeddings, in-memory vector store, local memory) unless overridden by `backend/.env`.

## Configure

All values live in `backend/.env` (gitignored). `backend/.env.example` documents every masked key.

- `LLM_PROVIDER`: `openai-compatible` / `nvidia` / `ollama` / `mock`
- `EMBEDDING_PROVIDER`: `openai-compatible` / `nvidia` / `mock`
- `VECTOR_STORE`: `zilliz` (cloud, requires `ZILLIZ_URI` + `ZILLIZ_TOKEN`) / `in-memory`
- `MEMORY_BACKEND`: `dynamodb` / `local`
- `LANGCHAIN_TRACING_V2`, `LANGSMITH_API_KEY`, `LANGCHAIN_PROJECT`: LangSmith tracing

## API

- `POST /goals` -> 201 `WorkflowState` (see `app/models/workflow.py`)
- `POST /goals/{workflow_id}/continue` body `{"completed_task_ids": [...]}`
- `GET /workflows` -> summaries; `GET /workflows/{workflow_id}` -> full state
- `POST /documents/ingest` multipart file upload -> `{filename, chunks}`
- `GET /health`

## Ingest documents

Drop PDF/TXT/MD files in `documents/` and run `py -3 scripts/ingest_documents.py`, or upload via the API. Run from the `backend/` directory.

## Tests

```powershell
py -3 -m pytest -q
```

51 tests: unit (models, validation, optimization, provider, RAG) + integration (service, API, workflow). Cloud tests are skipped unless `RUN_CLOUD_TESTS=1`.

## Nightly / E2E sanity

`scripts/e2e_server.py` (offline override) + `scripts/e2e_checks.py` exercise the full HTTP contract against a live server (32 checks).

## Known limitations

- Offline tools (mock LLM, local store) are for development, not production reasoning or concurrency.
- External workplace integrations, auth, task-mutation endpoints, and autonomous actions are not included.
- Dev container / Docker compose are provided but Docker is not installed in this environment.