# AI Workplace Operations Agent

An advisory agent that turns a workplace goal into a structured, validated action plan. FastAPI + LangGraph power the backend; a React + Vite app provides the web UI. The agent recommends actions but never executes workplace actions automatically.

## Layout

```
ActionPlan/
├── backend/          # Python API (FastAPI + LangGraph), memory, RAG, tests
│   ├── app/          # source
│   ├── scripts/      # run_api.py, ingest_documents.py
│   ├── tests/        # pytest suite (unit + integration + cloud)
│   ├── documents/    # procedure / policy documents to ingest
│   ├── .env          # secrets - gitignored, never committed
│   └── pyproject.toml
├── frontend/         # React Vite web UI
│   ├── src/          # source
│   └── dist/         # production build (served by the backend at /)
├── data/             # local memory + vector store (gitignored)
└── .gitignore
```

## Run the backend

```powershell
cd backend
py -3 -m pip install -e ".[test]"
py -3 scripts/run_api.py
```

By default the API serves on `http://127.0.0.1:8000` (`/docs` has the OpenAPI UI).

`run_api.py` defaults to a fully offline mock stack (mock LLM, in-memory vector store, local memory). To use cloud services, set the matching `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `VECTOR_STORE`, and `MEMORY_BACKEND` values in `backend/.env`.

## Run the frontend

Development server (hot reload) on `http://localhost:5173`:

```powershell
cd frontend
npm install
npm run dev
```

Production build (the backend then serves `frontend/dist` at `/`):

```powershell
cd frontend
npm run build
```

The frontend never talks to the cloud directly; it only calls the local backend at `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`).

## Test

```powershell
cd backend
py -3 -m pytest -q
```

The suite uses the mock provider and temporary local stores; it never calls a real LLM. Set `RUN_CLOUD_TESTS=1` to run the cloud integration tests.

## How it works

`FastAPI -> AgentService -> LangGraph -> typed domain models`

The graph analyzes the objective, extracts requirements and procedures, plans and validates an execution plan, optimizes the critical path, detects blockers, recommends the next action, and persists memory. `LLMProvider`, `VectorStore`, and `MemoryInterface` are extension boundaries (NVIDIA NIM / OpenAI-compatible / Ollama, Zilliz / in-memory, DynamoDB / local JSON).

## Security

`backend/.env` holds secrets and is gitignored. Only `backend/.env.example` (masked placeholders) is tracked. Never commit real credentials.