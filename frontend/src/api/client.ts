import type {
  IngestResponse,
  WorkRequestInput,
  WorkflowState,
  WorkflowSummary,
} from "./workflow-types";

const API_BASE_URL =
  import.meta.env.example.VITE_API_BASE_URL;

export type BackendStatus = "checking" | "active" | "inactive" | "error";

export class ApiError extends Error {
  status: number;
  type: "network" | "http" | "cors" | "unknown";

  constructor(status: number, message: string, type: "network" | "http" | "cors" | "unknown" = "unknown") {
    super(message);
    this.status = status;
    this.type = type;
  }
}

export async function checkBackendHealth(): Promise<BackendStatus> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (response.ok) {
      const data = await response.json();
      if (data.status === "ok") {
        return "active";
      }
      return "inactive";
    }
    return "inactive";
  } catch (err: unknown) {
    if (err instanceof TypeError && err.message.includes("fetch")) {
      return "error";
    }
    return "error";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the backend at ${API_BASE_URL}. Is the API running?", "network");
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
    const errorType: "http" | "cors" | "unknown" = response.status === 403 ? "cors" : "http";
    throw new ApiError(response.status, detail, errorType);
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
