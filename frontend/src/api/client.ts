import type {
  IngestResponse,
  WorkRequestInput,
  WorkflowState,
  WorkflowSummary,
} from "./workflow-types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the backend. Is the API running?");
  }
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // fall through with the default message
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function createGoalRequest(
  input: WorkRequestInput,
): Promise<WorkflowState> {
  return requestJson<WorkflowState>("/goals", jsonInit("POST", input));
}

export function continueGoalRequest(
  workflowId: string,
  completedTaskIds: string[],
): Promise<WorkflowState> {
  return requestJson<WorkflowState>(
    `/goals/${encodeURIComponent(workflowId)}/continue`,
    jsonInit("POST", { completed_task_ids: completedTaskIds }),
  );
}

export function getWorkflowRequest(workflowId: string): Promise<WorkflowState> {
  return requestJson<WorkflowState>(
    `/workflows/${encodeURIComponent(workflowId)}`,
  );
}

export function listWorkflowsRequest(): Promise<WorkflowSummary[]> {
  return requestJson<WorkflowSummary[]>("/workflows");
}

export async function ingestDocumentRequest(
  file: File,
): Promise<IngestResponse> {
  const body = new FormData();
  body.append("file", file);
  return requestJson<IngestResponse>("/documents/ingest", {
    method: "POST",
    body,
  });
}