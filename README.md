# AI Workplace Operations Agent

V1 of a cloud-oriented advisory agent for workplace operations. It accepts a high-level goal, decomposes it into a typed workflow, retrieves organizational evidence from Zilliz/Milvus, detects blockers, recommends the next best action, and persists workflow memory.

The agent recommends actions only. It does not execute Slack, Jira, GitHub, email, CI/CD, or other workplace actions.

## Architecture

Runtime flow:

```text
FastAPI -> AgentService -> LangGraph -> typed nodes -> memory/vector-store interfaces
```

LangGraph stages:

```text
START
  -> Analyze Goal
  -> Create / Update Plan
  -> Retrieve Relevant Knowledge
  -> Analyze Current State
  -> Detect Blockers
  -> Recommend Next Action
  -> Update Memory
  -> END
```

Core boundaries:

- `app/api`: thin FastAPI route handlers
- `app/agent`: LangGraph orchestration and node logic
- `app/models`: Pydantic domain schemas
- `app/llm`: OpenAI-compatible and Ollama model adapter
- `app/rag`: ingestion, embeddings, retriever, Zilliz vector-store adapter
- `app/memory`: `MemoryStore` protocol, DynamoDB adapter, local test/dev adapter
- `app/config.py`: centralized environment-based settings

## Prerequisites

- Python 3.11+
- Cloud LLM endpoint that supports OpenAI-compatible chat completions, or Ollama for local experiments
- Cloud embedding endpoint compatible with OpenAI embeddings
- Zilliz Cloud URI and token
- DynamoDB table if `MEMORY_BACKEND=dynamodb`

## Installation

```powershell
py -3 -m pip install -e ".[test]"
```

If this machine does not have a global Python launcher, use the bundled Python path from Codex:

```powershell
& "C:\Users\priya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -e ".[test]"
```

## Environment Configuration

Create `.env` from `.env.example` and fill in your cloud values. Do not commit `.env`.

Important variables:

- `LLM_PROVIDER=openai-compatible`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL`
- `EMBEDDING_PROVIDER=openai-compatible`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`
- `EMBEDDING_BASE_URL`
- `VECTOR_STORE=zilliz`
- `ZILLIZ_URI`
- `ZILLIZ_TOKEN`
- `ZILLIZ_COLLECTION`
- `MEMORY_BACKEND=dynamodb`
- `AWS_REGION`
- `DYNAMODB_TABLE_NAME`

`LLM_PROVIDER=nvidia` and `EMBEDDING_PROVIDER=nvidia` are accepted as aliases for OpenAI-compatible endpoints.

## Run The API

```powershell
py -3 scripts/run_api.py
```

Or with the bundled Python:

```powershell
& "C:\Users\priya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts/run_api.py
```

Open `http://127.0.0.1:8000/docs`.

## AWS Lambda Deployment (CodeBuild + API Gateway HTTP API)

The backend runs as a serverless FastAPI application on AWS Lambda behind
API Gateway HTTP API using the included Mangum adapter. The frontend stays on
Amplify and only has its `VITE_API_BASE_URL` environment variable repointed at
the API Gateway URL — no frontend code changes.

**Docker Desktop is NOT required.** Image building happens entirely in AWS CodeBuild.
The local machine only needs the AWS CLI and Git/source code.

Artifacts:

- `backend/lambda_handler.py` — Mangum adapter exposing `lambda_handler.handler`
- `backend/Dockerfile.lambda` — x86_64 container from the AWS Lambda Python 3.12
  base image; copies only `app/` + `lambda_handler.py` + pinned requirements
- `backend/requirements.txt` — pinned runtime dependencies (includes mangum)
- `backend/.dockerignore` — keeps secrets, tests, scripts, documents, and data
  out of the image
- `backend/buildspec.yml` — CodeBuild build specification
- `backend/scripts/deploy_lambda.ps1` — starts CodeBuild build, pushes image to ECR,
  updates the Lambda function
- `backend/infra/lambda/cloudformation-serverless.yaml` — CFN stack for the ECR repository,
  IAM execution role, Lambda function, CodeBuild project, CodeBuild IAM role, and CloudWatch log group
- `backend/scripts/cloud_smoke_test.py` — contract smoke test against any
  deployed base URL (`BACKEND_API_URL`)
- `backend/scripts/measure_goals_latency.py` — measures real POST /goals
  latency by phase (LLM, embeddings, Zilliz, DynamoDB, full graph)

Deployment steps:

1. Install the AWS CLI and authenticate (`aws configure`). Git/source code must be
   accessible to CodeBuild (e.g., a GitHub repository).
2. Provision AWS resources:

   ```powershell
   set-location backend
   aws cloudformation deploy --region us-east-2 --stack-name workplace-operations-serverless ^
     --template-file infra/lambda/cloudformation-serverless.yaml ^
     --parameter-overrides LambdaRoleName=workplace-operations-lambda-role `
     GitHubSourceLocation=https://github.com/<username>/<repo>.git ^
     --capabilities CAPABILITY_NAMED_IAM
   ```

   Note the `LambdaRoleArn`, `EcrRepositoryUri`, `CodeBuildProjectName`, and
   `LambdaFunctionName` from the stack outputs, or create equivalent resources
   yourself.

3. Set the Lambda environment variables (see below) — secrets are configured
   on the function, never baked into the image.
4. Build the Docker image in CodeBuild and update Lambda:

   ```powershell
   set-location backend
   .\scripts\deploy_lambda.ps1 -FunctionName workplace-operations-agent `
     -LambdaRoleArn arn:aws:iam::<account-id>:role/workplace-operations-lambda-role
   ```

   This starts a CodeBuild build that clones the repository, builds the
   Docker image using `Dockerfile.lambda`, pushes it to ECR, and updates
   the Lambda function to the new image. No local Docker is required.
5. Create an API Gateway HTTP API targeting the function (`$default` stage).
   The integration type is Lambda proxy. API Gateway HTTP API enforces a
   30-second integration timeout.
6. In the Amplify console for the frontend, set
   `VITE_API_BASE_URL=https://<api-id>.execute-api.us-east-2.amazonaws.com`
   and redeploy. Set the Lambda `FRONTEND_ORIGIN` to the Amplify URL.
7. Smoke test the deployed URL:

   ```powershell
   $env:BACKEND_API_URL = "https://<api-id>.execute-api.us-east-2.amazonaws.com"
   py -3 scripts/cloud_smoke_test.py
   ```

### Lambda environment variables

All configuration that comes from earlier phases can go in the template; all
secrets and Cloud-specific values must be set on the deployed function:

- Provider secrets: `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_PROVIDER`,
  `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_MODEL_API`,
  `EMBEDDING_BASE_URL`
- Zilliz: `ZILLIZ_URI`, `ZILLIZ_TOKEN`, `VECTOR_STORE=zilliz`,
  `ZILLIZ_COLLECTION`
- LangSmith (optional): `LANGCHAIN_TRACING_V2`, `LANGSMITH_API_KEY`,
  `LANGCHAIN_PROJECT`
- Memory: `MEMORY_BACKEND=dynamodb`, `DYNAMODB_TABLE_NAME=ActionPlanner`,
  `AWS_REGION=us-east-2`
- Lambda-only: `DATA_DIR=/tmp/data` (Lambda's writeable storage), and
  `FRONTEND_ORIGIN=https://<amplify-app>.amplifyapp.com` for browser CORS

No AWS credentials belong in the environment — the execution role grants the
function access to DynamoDB. Lambda runs with 2048 MB memory and a 60-second
timeout; ephemeral storage defaults to 1024 MB.

### Latency and the 30-second API Gateway ceiling

`POST /goals` runs the full LangGraph workflow synchronously (multiple typed
LLM calls plus embeddings + Zilliz retrieval). Measured against the real cloud
stack, a single NVIDIA LLM analysis call alone took over 120 seconds (it
timed out at the provider's configured 120 s timeout). This far exceeds the
30 s integration timeout of API Gateway HTTP API, so a fully synchronous
serverless deployment cannot serve `POST /goals` end to end today.

Options to move beyond the 30 s ceiling (not implemented here):

- Front the API with a small orchestration endpoint: `POST /goals` returns
  `202 Accepted` immediately with a `workflow_id` and a status URL, then a
  background executor (e.g. SQS + a second worker Lambda, Step Functions, or
  EventBridge) builds the workflow. The frontend polls or subscribes.
- The graph nodes that call the LLM/embeddings are independent per workflow,
  so the plan build can be moved fully off the request path.
- API Gateway REST APIs also cap integration timeouts; a separate
  asynchronous execution path is required either way.

Until an async path exists, the local/development server (uvicorn) is the
only way to run `POST /goals` synchronously within a single HTTP request.

### CodeBuild costs and free-tier notes

CodeBuild charges per build minute. The standard build image with
`BUILD_GENERAL1_SMALL` is free-tier eligible (750 build minutes/month
for the first 12 months on AWS Free Tier). ECR storage costs are minimal
for a single repository. Lambda is pay-per-invocation. This is a
portfolio project with low expected traffic, so costs should remain
near-free.

## Ingest Documents

Place `.pdf`, `.txt`, or `.md` files in `documents/`, then run:

```powershell
py -3 scripts/ingest_documents.py
```

The ingestion pipeline extracts text with PyMuPDF for PDFs, chunks text, generates cloud embeddings through LangChain, stores chunks in Zilliz, and preserves metadata: `source`, `filename`, `page`, and `document_type`.

You can also upload a single document:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/documents/ingest -Form @{ file = Get-Item ".\documents\security_policy.pdf" }
```

## Example API Requests

Create a workflow:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/goals -ContentType "application/json" -Body '{"goal":"Prepare Project Alpha for production"}'
```

Get workflow state:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/workflows/{workflow_id}
```

Continue/re-evaluate:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/workflows/{workflow_id}/continue
```

## Run Tests

```powershell
py -3 -m pytest -q
```

Tests mock LLM and embedding behavior and use an in-memory vector store. They
do not call OpenAI-compatible providers, Zilliz, LangSmith, or AWS. Lambda
adapter tests (`tests/lambda/`) exercise the Mangum handler with mocked
components and representative API Gateway HTTP API events.

## Enable LangSmith

LangSmith is optional. Set:

```text
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=workplace-operations-agent
```

LangChain/LangGraph will trace the graph stages when these variables are present. If they are absent or tracing is false, the app runs normally.

## Architectural Notes

The LLM is used for goal interpretation and task decomposition. Deterministic Python logic validates dependency integrity, detects dependency cycles, selects current tasks, and identifies missing evidence.

RAG evidence is modeled separately from assumptions. Recommendations include evidence metadata when retrieved chunks are available and identify missing organizational knowledge as a blocker when the vector store has no relevant evidence.

Memory has two conceptual layers: persisted short-term workflow state and simple long-term cross-workflow notes. `MemoryStore` allows DynamoDB and future Cosmos DB implementations without changing the graph.

## Known Limitations

- V1 is advisory only and never executes external workplace actions.
- Task completion updates are represented in persisted workflow state but there is no dedicated mutation endpoint yet.
- Long-term memory is intentionally simple.
- Zilliz collection schema/index customization is minimal.
- No authentication, authorization, UI, or production deployment hardening is included.
- No real cloud calls are made by tests.

## Future V2 Improvements

- Task state mutation endpoints with audit history
- Human approval gates for external actions
- Jira/GitHub/Slack/Teams/email integrations behind explicit action boundaries
- Cosmos DB memory adapter
- Richer document management and re-ingestion controls
- Evaluation datasets for goal analysis and recommendation quality
- Multi-user authentication and authorization
- Deployment manifests and production observability dashboards
