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

60 tests: unit (models, validation, optimization, provider, RAG, cloud
embeddings adapter) + integration (service, API, workflow) + Lambda adapter
(`tests/lambda/` runs the Mangum handler with mocked components). Cloud tests
are skipped unless `RUN_CLOUD_TESTS=1`.

## Nightly / E2E sanity

`scripts/e2e_server.py` (offline override) + `scripts/e2e_checks.py` exercise the full HTTP contract against a live server (32 checks).

## AWS Lambda deployment

Container image on Lambda via Mangum + API Gateway HTTP API. Image
builds happen entirely in **AWS CodeBuild** — Docker Desktop is NOT
required locally. The local machine only needs the AWS CLI and Git/source code.

Full steps live in the root `README.md`; quick reference:

- `lambda_handler.py` — Mangum adapter (`handler = Mangum(app, lifespan="off")`)
- `Dockerfile.lambda` — `public.ecr.aws/lambda/python:3.12`, x86_64, copies only
  `app/` + `requirements.txt` + `lambda_handler.py`, `ENV DATA_DIR=/tmp/data`
- `buildspec.yml` — CodeBuild build specification
- `scripts/deploy_lambda.ps1` — starts CodeBuild build, pushes image to ECR,
  updates Lambda function
- `infra/lambda/cloudformation-serverless.yaml` — CFN stack for role, ECR repo,
  Lambda function, CodeBuild project, CodeBuild IAM role, CloudWatch log group
- `scripts/cloud_smoke_test.py` (`BACKEND_API_URL`),
  `scripts/measure_goals_latency.py` (phase-by-phase timing)

Secrets (`LLM_API_KEY`, `ZILLIZ_TOKEN`, ...) go into Lambda environment
variables, never the image. AWS access comes from the execution role, not env
vars. Set `FRONTEND_ORIGIN` to the Amplify URL; point the frontend at the API
Gateway URL via its `VITE_API_BASE_URL` env var.

Measured real-cloud `POST /goals` latency: the first NVIDIA LLM analysis call
alone exceeded the provider's 120 s timeout, far past API Gateway HTTP API's
30 s integration cap — so the synchronous path is not serverless-deployable
end to end; see root README for async options (not implemented).

## Known limitations

- Offline tools (mock LLM, local store) are for development, not production reasoning or concurrency.
- External workplace integrations, auth, task-mutation endpoints, and autonomous actions are not included.
- Docker is not installed in this environment; image builds happen in AWS CodeBuild instead.
- The Zilliz `workplace_documents` collection was re-created with the adapter's
  schema (`app/rag/zilliz.py`). The adapter now auto-creates the AUTOINDEX and
  loads the collection before searching, so a fresh deployment works without
  manual steps; re-ingest (`scripts/ingest_documents.py` or the
  `/documents/ingest` endpoint) after any reset.
- CodeBuild source requires a Git repository accessible to CodeBuild (e.g., GitHub).