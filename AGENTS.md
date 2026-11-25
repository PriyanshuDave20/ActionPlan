# Repository Guidelines

## Project Structure & Module Organization

- `backend/`: FastAPI + LangGraph service. Application code is in `backend/app/` (`api`, `agent`, `models`, `llm`, `rag`, `memory`); operational scripts are in `backend/scripts/`; document fixtures/uploads belong in `backend/documents/`.
- `backend/tests/`: Python tests organized as `unit/`, `integration/`, `lambda/`, and opt-in `cloud/` tests.
- `frontend/`: React + TypeScript + Vite client. Components/application entry points are in `src/`; API clients and hooks are in `src/api/` and `src/lib/`.
- Root files contain repository-level deployment/build configuration (`buildspec.yml`) and documentation.

## Build, Test, and Development Commands

Backend (run from `backend/`):

```powershell
py -3 -m pip install -e ".[test]"
py -3 scripts/run_api.py
py -3 -m pytest -q
```

- Install the editable backend with test dependencies.
- Run the API locally, using offline mock defaults unless `backend/.env` overrides them.
- Run backend unit, integration, and Lambda tests. Set `RUN_CLOUD_TESTS=1` to include cloud tests.

Frontend (run from `frontend/`):

```powershell
npm install
npm run dev
npm run build
npm run test
```

- Install dependencies, start Vite on port 5173, or run the TypeScript build check and production bundle.
- Run Vitest unit tests.

## Coding Style & Naming Conventions

- Python targets 3.11+, uses 4-space indentation, type hints for public interfaces, and a 100-character line limit. Keep route logic thin and put workflow/domain behavior under `app/agent`, `app/models`, or the relevant service module.
- TypeScript uses strict mode, ES modules, 2-space indentation, descriptive `PascalCase` components/types, and `camelCase` variables/functions.
- Prefer focused, descriptive names; avoid committed generated artifacts, caches, and backup files such as `.bak`.

## Testing Guidelines

- Add Pytest tests under the matching backend test directory; name files `test_*.py` and functions `test_*`.
- Cover API behavior, workflow transitions, adapters, and model validation for backend changes.
- Frontend currently has no dedicated test framework; `npm run build` is the required type/build regression check.

## Commit & Pull Request Guidelines

- Recent commits use short, imperative summaries such as `fix routing` and `refactor frontend`. Keep subjects concise and one logical change per commit.
- Pull requests should describe the change, list manual/automated verification commands, link related issues, and include screenshots or API examples for UI or endpoint changes.
- Never commit `.env`, API keys, tokens, AWS credentials, or local database state. Copy configuration examples from `*.env.example`.
- Set `API_TOKENS` in deployed environments to require bearer-token authentication.
